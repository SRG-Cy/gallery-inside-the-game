"""Rule-based key-moment detection over the live event stream."""
from collections import Counter

from gallery.models import Event, Moment
from gallery.stats.engine import TEAMS, StatsEngine, in_box, progress

WINDOW = 300.0
COOLDOWN = 600.0
MOMENTUM_CHECK_EVERY = 30.0
MILESTONES = (50, 75, 100)
MIN_MOMENTUM_T = 600.0  # momentum needs ten minutes of play before it means anything


class Detectors:
    def __init__(self, stats: StatsEngine):
        self.stats = stats
        self.completed = Counter()
        self.last_fired: dict[tuple[str, str], float] = {}
        self.last_momentum_check = float("-inf")
        self.momentum_leader: str | None = None

    def _cooled(self, kind: str, team: str, t: float) -> bool:
        last = self.last_fired.get((kind, team))
        return last is None or t - last >= COOLDOWN

    def _moment(self, kind: str, e: Event, priority: int, evidence: list[int], stats: dict,
                team: str | None = None, player_id: str | None = None) -> Moment:
        return Moment(kind=kind, t=e.t, team=team if team is not None else e.team,
                      player_id=player_id if player_id is not None else e.player_id,
                      evidence_event_ids=evidence[-10:], stats=stats, priority=priority)

    def check(self, e: Event) -> list[Moment]:
        out: list[Moment] = []
        s = self.stats
        if e.type == "goal":
            chain = [x.id for x in s.events[-12:] if x.team == e.team][-9:]
            out.append(self._moment("goal", e, 3, chain + ([e.id] if e.id not in chain else []), {
                "team": s.team(e.team), "player": s.player(e.player_id), "score": s.snapshot()["score"]}))
        if (e.type == "shot" and e.outcome != "goal" and in_box(e.team, e.x, e.y)
                and e.meta.get("xg", 1) >= 0.25):
            out.append(self._moment("big_chance", e, 2, [e.id], {
                "player": s.player(e.player_id), "xg": e.meta.get("xg"), "outcome": e.outcome}))
        if (e.type == "sprint" and (e.speed_kmh or 0) >= 33) or (
                e.type == "shot" and (e.speed_kmh or 0) >= 100):
            out.append(self._moment("speed", e, 1, [e.id], {
                "player": s.player(e.player_id), "speed_kmh": e.speed_kmh, "action": e.type}))
        if e.type == "pass" and e.outcome == "complete":
            self.completed[e.player_id] += 1
            n = self.completed[e.player_id]
            if n in MILESTONES:
                out.append(self._moment("milestone", e, 1, [e.id], {
                    "player": s.player(e.player_id), "milestone": n}))
        if e.type == "pressure" and self._cooled("pressing_surge", e.team, e.t):
            m = self._pressing(e)
            if m:
                out.append(m)
        if e.type == "substitution":
            out.append(self._moment("tactical_shift", e, 2, [e.id], {
                "team": s.team(e.team), "on": s.player(e.player_id),
                "off": s.player(e.meta["off"]) if e.meta.get("off") else None}))
        if e.t - self.last_momentum_check >= MOMENTUM_CHECK_EVERY:
            self.last_momentum_check = e.t
            m = self._momentum(e)
            if m:
                out.append(m)
        return out

    def _pressing(self, e: Event) -> Moment | None:
        start = e.t - WINDOW
        pressures = [x for x in self.stats.events if x.type == "pressure" and x.team == e.team]
        recent = [x for x in pressures if x.t > start]
        before_min = start / 60
        if before_min < 5 or len(recent) < 6:
            return None
        baseline = (len(pressures) - len(recent)) / before_min
        rate = len(recent) / (WINDOW / 60)
        if rate < 1.8 * max(baseline, 0.5):
            return None
        self.last_fired[("pressing_surge", e.team)] = e.t
        s = self.stats
        return self._moment("pressing_surge", e, 3, [x.id for x in recent], {
            "team": s.team(e.team),
            "window_now": s.window(e.team, start, e.t + 0.001),
            "window_before": s.window(e.team, start - WINDOW, start),
            "rate_per_min": round(rate, 1), "baseline_per_min": round(baseline, 1),
            "high_press_share_pct": round(100 * sum(progress(e.team, x.x) > 52.5 for x in recent)
                                          / len(recent)),
        }, player_id="")

    def _momentum(self, e: Event) -> Moment | None:
        teams = {t: self.stats.team(t) for t in TEAMS}
        nor = teams["NOR"]["momentum"]
        leader = "NOR" if nor >= 70 else "HAR" if nor <= 30 else None
        if leader is None or leader == self.momentum_leader:
            return None
        previous, self.momentum_leader = self.momentum_leader, leader
        if previous is None or e.t < MIN_MOMENTUM_T or not self._cooled("momentum_swing", "any", e.t):
            return None
        self.last_fired[("momentum_swing", "any")] = e.t
        evidence = [x.id for x in self.stats.events
                    if x.team == leader and x.type == "shot" and e.t - x.t < WINDOW]
        return self._moment("momentum_swing", e, 3, evidence, {
            "team": teams[leader], "momentum": {t: teams[t]["momentum"] for t in TEAMS},
            "previous_leader": previous}, team=leader, player_id="")
