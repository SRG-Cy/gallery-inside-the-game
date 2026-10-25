"""The agent crew: Analyst -> Verifier -> Graphics -> Verifier for each moment, then Personalizer
and Recap after the producer approves. Every failure path ends in a verified template."""
import json
import time

from pydantic import ValidationError

from gallery.agents import prompts, templates
from gallery.agents.tools import make_tools
from gallery.agents.verifier import verify, verify_text
from gallery.llm import LLM, parse_json
from gallery.models import Insight, Moment, Overlay, Proposal
from gallery.sim.squads import PLAYERS, TEAMS
from gallery.stats.engine import StatsEngine

SHELF_LIFE = 120.0
TEMPLATE_ONLY = {"speed", "milestone"}
VARIANTS = ("casual", "analyst", "player", "es")


def _moment_prompt(m: Moment) -> str:
    people = {pid: PLAYERS[pid].name for pid in {m.player_id} if pid in PLAYERS}
    return (f"MOMENT: {m.kind} at {int(m.t // 60)}' for {TEAMS.get(m.team or '', 'n/a')} ({m.team})\n"
            f"PLAYERS: {json.dumps(people)}\n"
            f"EVIDENCE EVENT IDS: {m.evidence_event_ids}\n"
            f"FACTS: {json.dumps(m.stats, sort_keys=True)}")


class Crew:
    def __init__(self, llm: LLM, stats: StatsEngine):
        self.llm = llm
        self.stats = stats
        self._seq = 0

    async def _call(self, trace: list[dict], agent: str, instructions: str, prompt: str, tools=()):
        start = time.perf_counter()
        try:
            text = await self.llm.run(agent, instructions, prompt, list(tools))
            trace.append({"agent": agent, "ms": round(1000 * (time.perf_counter() - start)), "ok": True})
            return text
        except Exception as exc:  # timeout, rate limit, replay miss, provider error
            trace.append({"agent": agent, "ms": round(1000 * (time.perf_counter() - start)),
                          "ok": False, "errors": [f"{type(exc).__name__}: {exc}"[:200]]})
            return None

    async def _analyst(self, m: Moment, frozen: StatsEngine, trace: list[dict]) -> Insight | None:
        prompt = _moment_prompt(m)
        for attempt in range(2):
            text = await self._call(trace, "analyst", prompts.ANALYST, prompt, make_tools(frozen))
            if text is None:
                return None
            try:
                insight = Insight.model_validate(parse_json(text))
                errors = verify(insight, frozen, m.t, facts=m.stats)
            except (ValueError, ValidationError) as exc:
                errors = [f"reply was not valid insight JSON: {str(exc)[:200]}"]
            trace.append({"agent": "verifier", "ms": 0, "ok": not errors, "errors": errors, "attempt": attempt + 1})
            if not errors:
                return insight
            prompt = (f"{_moment_prompt(m)}\n\nYOUR PREVIOUS DRAFT:\n{text}\n\n"
                      f"THE VERIFIER REJECTED IT:\n- " + "\n- ".join(errors) +
                      "\nFix every problem and reply with corrected JSON.")
        return None

    async def _graphics(self, m: Moment, insight: Insight, frozen: StatsEngine,
                        trace: list[dict]) -> Overlay | None:
        prompt = f"MOMENT: {m.kind}\nINSIGHT: {insight.model_dump_json()}"
        text = await self._call(trace, "graphics", prompts.GRAPHICS, prompt)
        if text is None:
            return None
        try:
            data = parse_json(text)
            overlay = Overlay(kind=data["kind"], title=data["title"], body=data["body"],
                              stats=[tuple(map(str, s)) for s in data.get("stats", [])][:3],
                              t_start=m.t, duration_s=12 if m.kind == "goal" else 8)
            shown = ". ".join([overlay.title, overlay.body] + [f"{k}: {v}" for k, v in overlay.stats])
            errors = verify_text(shown, frozen, m.t, facts=m.stats)
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            overlay, errors = None, [f"reply was not valid overlay JSON: {str(exc)[:200]}"]
        trace.append({"agent": "verifier", "ms": 0, "ok": not errors, "errors": errors})
        return overlay if not errors else None

    async def propose(self, m: Moment, now: float) -> Proposal:
        frozen = self.stats.frozen()
        trace: list[dict] = []
        insight = None if m.kind in TEMPLATE_ONLY else await self._analyst(m, frozen, trace)
        source = "agent" if insight else "template"
        overlay = None
        if insight:
            overlay = await self._graphics(m, insight, frozen, trace)
            if overlay is None:
                overlay = templates.overlay_for(m, insight)
        else:
            insight = templates.insight_for(m, frozen)
            overlay = templates.overlay_for(m, insight)
            trace.append({"agent": "template", "ms": 0, "ok": True})
        self._seq += 1
        return Proposal(id=f"p-{int(m.t)}-{m.kind}-{m.team or 'x'}-{self._seq}", moment=m, insight=insight,
                        overlay=overlay, source=source, verified=True, expires_at=now + SHELF_LIFE,
                        trace=trace)

    async def personalize(self, p: Proposal, player_id: str | None) -> dict[str, str]:
        fallback = templates.variants_for(p.insight, p.moment)
        facts = dict(p.moment.stats)
        focus = ""
        if player_id in PLAYERS:
            facts["focus_player"] = self.stats.player(player_id)
            focus = f"FOLLOWED PLAYER: {PLAYERS[player_id].name} ({player_id}) {json.dumps(facts['focus_player'])}\n"
        prompt = f"{focus}INSIGHT: {p.insight.model_dump_json()}\nFACTS: {json.dumps(p.moment.stats, sort_keys=True)}"
        text = await self._call(p.trace, "personalizer", prompts.PERSONALIZER, prompt)
        try:
            data = parse_json(text) if text else {}
        except ValueError:
            data = {}
        out = {}
        for key in VARIANTS:
            candidate = data.get(key)
            ok = isinstance(candidate, str) and candidate.strip() and not verify_text(
                candidate, self.stats, self.stats.now, facts=facts)
            out[key] = candidate if ok else fallback[key]
        return out

    async def recap(self, approved: list[Proposal], final: dict, period: str) -> str:
        trace: list[dict] = []
        prompt = (f"PERIOD: {period}\nSTATS: {json.dumps(final, sort_keys=True)}\n"
                  f"APPROVED INSIGHTS:\n" + "\n".join(f"- {p.insight.headline}: {p.insight.why_it_matters}"
                                                     for p in approved))
        text = await self._call(trace, "recap", prompts.RECAP, prompt)
        try:
            recap = parse_json(text)["recap"] if text else None
        except (ValueError, KeyError):
            recap = None
        if isinstance(recap, str) and not verify_text(recap, self.stats, self.stats.now, facts=final):
            return recap
        return self._template_recap(final, period)

    @staticmethod
    def _template_recap(final: dict, period: str) -> str:
        n, h = final["teams"]["NOR"], final["teams"]["HAR"]
        label = "Half-time" if period == "HT" else "Full-time"
        return (f"{label}: Northgate FC {n['goals']}, Harbour Athletic {h['goals']}. "
                f"Northgate had {n['possession_pct']}% of the ball and {n['shots']} shots; "
                f"Harbour Athletic replied with {h['shots']} shots at {h['pass_accuracy_pct']}% passing.")
