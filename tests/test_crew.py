import asyncio
import json

import pytest

from gallery.agents.crew import Crew
from gallery.sim.engine import simulate
from gallery.stats.detectors import Detectors
from gallery.stats.engine import StatsEngine
from tests.fakes import FakeLLM


def first_moment(kind: str):
    stats = StatsEngine()
    det = Detectors(stats)
    for e in simulate(7):
        stats.ingest(e)
        for m in det.check(e):
            if m.kind == kind:
                return stats, m
    raise AssertionError(kind)


@pytest.fixture
def surge():
    return first_moment("pressing_surge")


def analyst_reply(m, rate):
    return json.dumps({
        "headline": "Northgate squeeze the life out of the build-up" if m.team == "NOR"
        else "Harbour squeeze the life out of the build-up",
        "why_it_matters": "They are winning the ball back high and forcing hurried passes.",
        "claims": [{"text": f"{rate} pressures a minute", "metric": "rate_per_min",
                    "value": rate, "subject": m.team}],
        "evidence_event_ids": m.evidence_event_ids[:3],
    })


GRAPHICS = json.dumps({"kind": "lower_third", "title": "The press is on",
                       "body": "Winning the ball back high up the pitch.", "stats": []})


async def test_good_draft_is_verified_agent_source(surge):
    stats, m = surge
    llm = FakeLLM({"analyst": [analyst_reply(m, m.stats["rate_per_min"])], "graphics": [GRAPHICS]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "agent" and p.verified and p.status == "pending"
    assert p.overlay.title == "The press is on" and p.overlay.t_start == m.t
    assert p.expires_at == m.t + 120
    assert [s["agent"] for s in p.trace] == ["analyst", "verifier", "graphics", "verifier"]
    assert llm.calls[0]["tools"], "analyst must get stats tools"


async def test_bad_then_fixed_uses_revision(surge):
    stats, m = surge
    llm = FakeLLM({"analyst": [analyst_reply(m, 99.9), analyst_reply(m, m.stats["rate_per_min"])],
                   "graphics": [GRAPHICS]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert llm.count("analyst") == 2 and "rate_per_min" in llm.calls[1]["prompt"]
    assert "99.9" in llm.calls[1]["prompt"]
    assert p.source == "agent"


async def test_bad_twice_falls_back_to_template(surge):
    stats, m = surge
    llm = FakeLLM({"analyst": [analyst_reply(m, 99.9), "not json"], "graphics": [GRAPHICS]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "template" and p.verified
    assert llm.count("graphics") == 0


async def test_timeout_falls_back(surge):
    stats, m = surge
    llm = FakeLLM({"analyst": [asyncio.TimeoutError()]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "template" and llm.count("analyst") == 1
    assert p.trace[0]["ok"] is False


async def test_graphics_failure_keeps_agent_insight(surge):
    stats, m = surge
    llm = FakeLLM({"analyst": [analyst_reply(m, m.stats["rate_per_min"])], "graphics": ["oops"]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "agent" and p.overlay.title == p.insight.headline


async def test_live_stats_moving_on_does_not_break_verification(surge):
    stats, m = surge
    crew = Crew(FakeLLM(), stats)

    def reply(_prompt):
        for e in simulate(7)[len(stats.events):len(stats.events) + 300]:
            stats.ingest(e)  # the match keeps playing while the model thinks
        return analyst_reply(m, m.stats["rate_per_min"])

    crew.llm = FakeLLM({"analyst": [reply], "graphics": [GRAPHICS]})
    p = await crew.propose(m, now=m.t)
    assert p.source == "agent"


async def test_speed_moment_skips_llm():
    stats, m = first_moment("speed")
    llm = FakeLLM()
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert llm.calls == [] and p.source == "template" and p.overlay.kind == "player_tag"


async def test_personalize_rejects_hallucinated_number(surge):
    stats, m = surge
    llm = FakeLLM({"analyst": [analyst_reply(m, m.stats["rate_per_min"])], "graphics": [GRAPHICS]})
    crew = Crew(llm, stats)
    p = await crew.propose(m, now=m.t)
    llm.queues["personalizer"] = __import__("collections").deque([json.dumps({
        "casual": "They are pressing like mad.",
        "analyst": f"{m.stats['rate_per_min']} pressures per minute.",
        "player": "Okafor is at the heart of it.",
        "es": "Presión altísima: 999 recuperaciones.",
    })])
    v = await crew.personalize(p, "NOR-6")
    assert v["casual"] == "They are pressing like mad."
    assert "999" not in v["es"]
    assert set(v) == {"casual", "analyst", "player", "es"}


async def test_recap_falls_back_to_template(surge):
    stats, m = surge
    llm = FakeLLM({"recap": [RuntimeError("down")]})
    text = await Crew(llm, stats).recap([], stats.snapshot(), "HT")
    assert "Northgate FC" in text and "Harbour Athletic" in text


async def test_unverified_prose_with_failed_graphics_never_airs(surge):
    stats, m = surge
    bad = json.dumps({"headline": "Northgate have 97 shots", "why_it_matters": "They lead 9-0 with 812 passes.",
                      "claims": [], "evidence_event_ids": m.evidence_event_ids[:1]})
    llm = FakeLLM({"analyst": [bad, bad], "graphics": ["garbage"]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "template" and "97" not in p.overlay.title + p.overlay.body


async def test_graphics_stat_labels_are_verified(surge):
    stats, m = surge
    gfx = json.dumps({"kind": "stat_card", "title": "The press is on", "body": "Winning it back high.",
                      "stats": [["Rossi Bianchi 4 goals", str(m.stats["rate_per_min"])]]})
    llm = FakeLLM({"analyst": [analyst_reply(m, m.stats["rate_per_min"])], "graphics": [gfx]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert all("Rossi" not in label for label, _ in p.overlay.stats)


async def test_proposal_ids_unique_for_same_second_moments(surge):
    stats, m = surge
    crew = Crew(FakeLLM(), stats)
    s1 = await crew.propose(first_moment("speed")[1], now=0)
    s2 = await crew.propose(first_moment("speed")[1], now=0)
    assert s1.id != s2.id


async def test_window_figures_from_tools_are_verifiable(surge):
    stats, m = surge
    llm = FakeLLM()

    def reply(_prompt):
        compare = next(t for t in llm.calls[-1]["tools"] if t.__name__ == "compare_windows")
        r = compare(m.team, 5)
        value = r["last"]["pressures"]
        return json.dumps({"headline": "The press is biting", "why_it_matters": f"{value} pressures in the last five minutes.",
                           "claims": [{"text": "pressures", "metric": f"{r['metric_prefix']}.last.pressures",
                                       "value": value, "subject": m.team}],
                           "evidence_event_ids": m.evidence_event_ids[:2]})
    llm.queues["analyst"] = __import__("collections").deque([reply])
    llm.queues["graphics"] = __import__("collections").deque([GRAPHICS])
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "agent", p.trace
    assert p.moment.stats["windows"], "window facts travel with the proposal for later checks"


async def test_window_claims_verify_without_the_tool_having_run(surge):
    """Replay returns cached text without executing tools; window claims must still verify."""
    from gallery.agents.tools import window_facts
    stats, m = surge
    value = window_facts(stats.frozen(), m.team, 5)["last"]["pressures"]
    reply = json.dumps({"headline": "The press is biting", "why_it_matters": f"{value} pressures in the last five minutes.",
                        "claims": [{"text": "pressures", "metric": f"windows.{m.team}_5.last.pressures",
                                    "value": value, "subject": m.team}],
                        "evidence_event_ids": m.evidence_event_ids[:2]})
    llm = FakeLLM({"analyst": [reply], "graphics": [GRAPHICS]})
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "agent", p.trace


async def test_personalize_prompt_does_not_depend_on_when_it_is_approved(surge):
    stats, m = surge
    llm = FakeLLM({"analyst": [analyst_reply(m, m.stats["rate_per_min"])], "graphics": [GRAPHICS]},
                  default="not json")
    crew = Crew(llm, stats)
    p = await crew.propose(m, now=m.t)
    await crew.personalize(p, "NOR-6")
    for e in simulate(7)[len(stats.events):len(stats.events) + 400]:
        stats.ingest(e)  # the producer approves a few minutes later
    await crew.personalize(p, "NOR-6")
    prompts_seen = [c["prompt"] for c in llm.calls if c["agent"] == "personalizer"]
    assert prompts_seen[0] == prompts_seen[1]


async def test_agents_see_the_match_as_of_the_moment_even_if_proposed_late(surge):
    stats, m = surge
    expected = stats.until(m.event_id).team(m.team)
    for e in simulate(7)[len(stats.events):len(stats.events) + 30]:
        stats.ingest(e)  # the runtime ingests the rest of the tick before the crew task runs
    llm = FakeLLM()

    def reply(_prompt):
        team_stats = next(t for t in llm.calls[-1]["tools"] if t.__name__ == "get_team_stats")
        assert team_stats(m.team) == expected
        return analyst_reply(m, m.stats["rate_per_min"])
    llm.queues["analyst"] = __import__("collections").deque([reply])
    llm.queues["graphics"] = __import__("collections").deque([GRAPHICS])
    p = await Crew(llm, stats).propose(m, now=m.t)
    assert p.source == "agent", p.trace
