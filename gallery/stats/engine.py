"""Deterministic match statistics. Every number the product shows comes from here."""
import math

from gallery.models import PITCH_X, PITCH_Y, Event
from gallery.sim.squads import PLAYERS, STARTERS

TEAMS = ("NOR", "HAR")
MOMENTUM_WINDOW = 300.0
POSSESSION_TYPES = {"pass", "carry", "shot", "possession_change"}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def progress(team: str, x: float) -> float:
    """Distance travelled towards the opponent goal (NOR attacks +x)."""
    return x if team == "NOR" else PITCH_X - x


def in_box(team: str, x: float, y: float) -> bool:
    return progress(team, x) > 88.5 and abs(y - PITCH_Y / 2) < 20.16


def _pass_len(e: Event) -> float:
    return math.hypot((e.end_x or e.x) - e.x, (e.end_y or e.y) - e.y)


class StatsEngine:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.by_id: dict[int, Event] = {}

    def ingest(self, e: Event) -> None:
        self.events.append(e)
        self.by_id[e.id] = e

    @property
    def now(self) -> float:
        return self.events[-1].t if self.events else 0.0

    @staticmethod
    def pass_difficulty(e: Event) -> float:
        gain = progress(e.team, e.end_x if e.end_x is not None else e.x) - progress(e.team, e.x)
        d = 1 + _pass_len(e) / 8 + 2 * e.under_pressure + 1.5 * (gain > 15)
        return round(_clamp(d, 1, 10), 1)

    # --- team ---------------------------------------------------------------------------
    def _possession(self, events: list[Event]) -> dict[str, float]:
        held = {t: 0.0 for t in TEAMS}
        holder, since = None, 0.0
        for e in events:
            if holder:
                held[holder] += e.t - since
            since = e.t
            if e.type in POSSESSION_TYPES and e.team in TEAMS:
                holder = e.team
            if e.type in ("period_end", "goal"):
                holder = None
        return held

    def _momentum_raw(self, team: str, events: list[Event], now: float) -> float:
        raw = 0.0
        for e in events:
            age = now - e.t
            if e.team != team or age < 0 or age >= MOMENTUM_WINDOW:
                continue
            w = 1 - age / MOMENTUM_WINDOW
            if e.type == "shot":
                raw += w * (3 + 5 * in_box(team, e.x, e.y))
            elif e.type in ("pass", "carry") and e.outcome != "incomplete" and e.end_x is not None:
                if progress(team, e.x) < 70 <= progress(team, e.end_x):
                    raw += w
        return raw

    def _team_stats(self, team: str, events: list[Event], now: float) -> dict:
        opp = "HAR" if team == "NOR" else "NOR"
        mine = [e for e in events if e.team == team]
        passes = [e for e in mine if e.type == "pass"]
        done = sum(e.outcome == "complete" for e in passes)
        shots = [e for e in mine if e.type == "shot"]
        pressures = [e for e in mine if e.type == "pressure"]
        held = self._possession(events)
        total = sum(held.values())
        start = events[0].t if events else 0.0
        minutes = max(1.0, (now - start) / 60)
        m_mine, m_opp = (self._momentum_raw(t, events, now) for t in (team, opp))
        recent = [e for e in events if now - e.t < MOMENTUM_WINDOW]
        lost = sum(e.type == "possession_change" and e.team == opp for e in recent)
        r_passes = [e for e in recent if e.type == "pass" and e.team == team]
        r_acc = 100 * sum(e.outcome == "complete" for e in r_passes) / len(r_passes) if r_passes else 100
        window_min = max(1.0, min(MOMENTUM_WINDOW, now - start) / 60)
        tpm = lost / window_min
        return {
            "goals": sum(e.type == "goal" for e in mine),
            "possession_pct": round(100 * held[team] / total) if total else 50,
            "passes": len(passes),
            "pass_accuracy_pct": round(100 * done / len(passes)) if passes else 0,
            "shots": len(shots),
            "shots_on_target": sum(e.outcome in ("goal", "saved") for e in shots),
            "pressures": len(pressures),
            "pressures_per_min_opp_half": round(
                sum(progress(team, e.x) > PITCH_X / 2 for e in pressures) / minutes, 1),
            "momentum": round(100 * m_mine / (m_mine + m_opp)) if m_mine + m_opp else 50,
            "control_chaos": round(_clamp(100 * tpm / 4 * (1 - r_acc / 100 + 0.5), 0, 100)),
        }

    def team(self, code: str) -> dict:
        return self._team_stats(code, self.events, self.now)

    def window(self, team: str, t0: float, t1: float) -> dict:
        events = [e for e in self.events if t0 <= e.t < t1]
        return self._team_stats(team, events, min(t1, self.now))

    # --- player -------------------------------------------------------------------------
    def _minutes_on_pitch(self, pid: str) -> float:
        p = PLAYERS[pid]
        on = 0.0 if p.number <= STARTERS else None
        off = None
        for e in self.events:
            if e.type == "substitution":
                if e.player_id == pid:
                    on = e.t
                elif e.meta.get("off") == pid:
                    off = e.t
        if on is None:
            return 0.0
        return max(0.0, ((off if off is not None else self.now) - on) / 60)

    def player(self, pid: str) -> dict:
        mine = [e for e in self.events if e.player_id == pid]
        passes = [e for e in mine if e.type == "pass"]
        done = sum(e.outcome == "complete" for e in passes)
        sprints = [e for e in mine if e.type == "sprint"]
        shots = [e for e in mine if e.type == "shot"]
        carried = sum(_pass_len(e) for e in mine if e.type == "carry")
        sprinted = sum(e.meta.get("distance_m", 0) for e in sprints)
        return {
            "name": PLAYERS[pid].name,
            "team": PLAYERS[pid].team,
            "passes": len(passes),
            "passes_completed": done,
            "pass_accuracy_pct": round(100 * done / len(passes)) if passes else 0,
            "avg_pass_m": round(sum(map(_pass_len, passes)) / len(passes), 1) if passes else 0.0,
            "avg_pass_difficulty": round(sum(map(self.pass_difficulty, passes)) / len(passes), 1)
            if passes else 0.0,
            "top_speed_kmh": max((e.speed_kmh or 0 for e in sprints), default=0.0),
            "distance_km": round(self._minutes_on_pitch(pid) * 0.105 + (carried + sprinted) / 1000, 2),
            "shots": len(shots),
            "top_shot_kmh": max((e.speed_kmh or 0 for e in shots), default=0.0),
        }

    def snapshot(self) -> dict:
        teams = {t: self.team(t) for t in TEAMS}
        return {"t": self.now, "minute": int(self.now // 60), "teams": teams,
                "score": {t: teams[t]["goals"] for t in TEAMS}}
