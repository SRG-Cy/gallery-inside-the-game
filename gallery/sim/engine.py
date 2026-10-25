"""Seeded football match simulator.

Play is a sequence of possession chains. Each action advances the clock a few seconds and may
emit pressures, sprints, fouls and turnovers. A per-minute intensity schedule layers scripted
story beats (a Northgate pressing spell, a Harbour momentum spell, one goal each) over random play.
"""
import math
import random

from gallery.models import PITCH_X, PITCH_Y, Event
from gallery.sim.squads import SQUADS, STARTERS

HALF = 45 * 60
FULL = 90 * 60
SUB_MINUTES = (62, 71, 80)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class _Sim:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.events: list[Event] = []
        self.t = 0.0
        self.score = {"NOR": 0, "HAR": 0}
        self.on_pitch = {t: [p.id for p in SQUADS[t][:STARTERS]] for t in SQUADS}
        self.bench = {t: [p.id for p in SQUADS[t][STARTERS:]] for t in SQUADS}
        self.positions = {p.id: p.position for t in SQUADS for p in SQUADS[t]}
        # Scripted goals: team -> minute after which its next chain ends in a goal.
        self.goal_script = {"NOR": 58 + self.rng.random() * 3, "HAR": 74 + self.rng.random() * 3}

    # --- schedule -------------------------------------------------------------------------
    def minute(self) -> float:
        return self.t / 60

    def press(self, team: str) -> float:
        m = self.minute()
        if team == "NOR" and 55 <= m < 63:
            return 1.0
        if team == "HAR" and 70 <= m < 78:
            return 0.3
        return 0.2

    def attack(self, team: str) -> float:
        m = self.minute()
        if team == "HAR" and 70 <= m < 78:
            return 1.7
        if team == "NOR" and 70 <= m < 78:
            return 0.6
        return 1.0

    # --- helpers --------------------------------------------------------------------------
    def emit(self, type_: str, team: str, player_id: str | None, x: float, y: float, **kw) -> Event:
        e = Event(id=len(self.events) + 1, t=round(self.t, 1), type=type_, team=team,
                  player_id=player_id, x=round(_clamp(x, 0, PITCH_X), 1),
                  y=round(_clamp(y, 0, PITCH_Y), 1), **kw)
        self.events.append(e)
        return e

    def outfield(self, team: str, exclude: str | None = None) -> list[str]:
        return [p for p in self.on_pitch[team] if self.positions[p] != "GK" and p != exclude]

    def pick(self, team: str, exclude: str | None = None) -> str:
        players = self.outfield(team, exclude)
        weights = [3.0 if self.positions[p] in ("CM", "AM") else 1.0 for p in players]
        if team == "NOR":  # Okafor (NOR-6) is the metronome and hits the pass milestones.
            weights = [w * 2.0 if p == "NOR-6" else w for p, w in zip(players, weights)]
        return self.rng.choices(players, weights)[0]

    @staticmethod
    def other(team: str) -> str:
        return "HAR" if team == "NOR" else "NOR"

    @staticmethod
    def progress(team: str, x: float) -> float:
        return x if team == "NOR" else PITCH_X - x

    @staticmethod
    def to_abs(team: str, p: float) -> float:
        return p if team == "NOR" else PITCH_X - p

    def tick(self, lo: float, hi: float) -> None:
        self.t += self.rng.uniform(lo, hi)

    # --- play -----------------------------------------------------------------------------
    def substitutions(self) -> None:
        for team in ("NOR", "HAR"):
            due = sum(1 for m in SUB_MINUTES if self.minute() >= m)
            made = 3 - len(self.bench[team])
            if made < due and self.bench[team]:
                off = self.rng.choice(self.outfield(team))
                on = self.bench[team].pop(0)
                self.on_pitch[team][self.on_pitch[team].index(off)] = on
                self.emit("substitution", team, on, 52.5, 0, meta={"off": off})

    def shot(self, team: str, holder: str, x: float, y: float, force_goal: bool) -> str:
        """Returns the team that restarts play."""
        goal_x = PITCH_X if team == "NOR" else 0.0
        dist = math.hypot(goal_x - x, PITCH_Y / 2 - y)
        xg = round(_clamp(0.6 * math.exp(-dist / 9), 0.02, 0.75), 2)
        if force_goal:
            outcome = "goal"
        else:
            r = self.rng.random()
            outcome = ("goal" if r < xg * 0.3 else "saved" if r < 0.45
                       else "blocked" if r < 0.65 else "off_target")
        speed = round(self.rng.uniform(62, 118), 1)
        self.emit("shot", team, holder, x, y, end_x=goal_x, end_y=PITCH_Y / 2 + self.rng.uniform(-4, 4),
                  outcome=outcome, speed_kmh=speed, meta={"xg": xg, "distance_m": round(dist, 1)})
        if outcome == "goal":
            self.score[team] += 1
            self.tick(1, 2)
            self.emit("goal", team, holder, goal_x, PITCH_Y / 2, meta={"score": dict(self.score)})
            if force_goal:
                self.goal_script.pop(team, None)
            self.tick(40, 70)
            return self.other(team)
        self.tick(4, 10)
        return self.other(team)

    def chain(self, team: str, x: float, y: float) -> tuple[str, float, float]:
        """Plays one possession; returns (next team in possession, x, y)."""
        opp = self.other(team)
        holder = self.pick(team)
        force_goal = team in self.goal_script and self.minute() >= self.goal_script[team]
        for _ in range(40):
            if self.t >= self.period_end:
                return team, x, y
            p = self.progress(team, x)
            pressed = False
            if self.rng.random() < self.press(opp) * (0.6 + p / 105):
                presser = self.pick(opp)
                self.emit("pressure", opp, presser, x, y, meta={"on": holder})
                pressed = True
                if self.rng.random() < 0.04:
                    self.emit("foul", opp, presser, x, y)
                    if self.rng.random() < 0.25:
                        self.emit("card", opp, presser, x, y, meta={"color": "yellow"})
                    self.tick(15, 30)
                    continue
                if self.rng.random() < 0.18 / self.attack(team):
                    self.emit("tackle", opp, presser, x, y, outcome="won")
                    self.emit("possession_change", opp, presser, x, y)
                    self.tick(1, 3)
                    return opp, x, y
            if self.rng.random() < 0.05:
                runner = self.pick(team)
                speed = round(_clamp(self.rng.gauss(29, 3), 22, 35.5), 1)
                self.emit("sprint", team, runner, x, y, speed_kmh=speed,
                          meta={"distance_m": round(self.rng.uniform(15, 45), 1)})
            in_range = p > 82 and abs(y - PITCH_Y / 2) < 22
            shoot_p = 0.16 * self.attack(team) if in_range else 0.0
            if force_goal and p > 80:
                shoot_p = 1.0
            if self.rng.random() < shoot_p:
                return self.shot(team, holder, x, y, force_goal), PITCH_X / 2, PITCH_Y / 2
            if self.rng.random() < 0.2:
                adv = self.rng.gauss(8, 5) * self.attack(team)
                np_, ny = _clamp(p + adv, 2, 103), _clamp(0.85 * y + 0.15 * PITCH_Y / 2 + self.rng.gauss(0, 5), 2, 66)
                nx = self.to_abs(team, np_)
                self.emit("carry", team, holder, x, y, end_x=round(nx, 1), end_y=round(ny, 1))
                x, y = nx, ny
                self.tick(2, 5)
                continue
            receiver = self.pick(team, exclude=holder)
            adv = self.rng.gauss(5 + 4 * self.attack(team) + (8 if force_goal else 0), 10)
            np_ = _clamp(p + adv, 2, 103)
            ny = _clamp(0.7 * y + 0.3 * PITCH_Y / 2 + self.rng.gauss(0, 11), 2, 66)
            nx = self.to_abs(team, np_)
            dist = math.hypot(nx - x, ny - y)
            success = (0.9 - 0.14 * pressed - 0.005 * max(0.0, dist - 15) - 0.06 * (np_ > 80)
                       + 0.04 * (self.attack(team) - 1))
            ok = self.rng.random() < success
            self.emit("pass", team, holder, x, y, end_x=round(nx, 1), end_y=round(ny, 1),
                      outcome="complete" if ok else "incomplete", under_pressure=pressed,
                      meta={"receiver": receiver, "length_m": round(dist, 1)})
            self.tick(2, 4.5)
            if not ok:
                gainer = self.pick(opp)
                if self.rng.random() < 0.5:
                    self.emit("interception", opp, gainer, nx, ny, outcome="won")
                self.emit("possession_change", opp, gainer, nx, ny)
                return opp, nx, ny
            holder, x, y = receiver, nx, ny
        self.emit("possession_change", opp, self.pick(opp), x, y)
        return opp, x, y

    def run(self) -> list[Event]:
        team = "NOR"
        for half, start in ((1, 0.0), (2, float(HALF))):
            self.t = start
            self.period_end = start + HALF
            self.emit("period_start", "", None, PITCH_X / 2, PITCH_Y / 2, meta={"period": half})
            x, y = PITCH_X / 2, PITCH_Y / 2
            while self.t < self.period_end:
                self.substitutions()
                team, x, y = self.chain(team, x, y)
            self.t = self.period_end
            self.emit("period_end", "", None, PITCH_X / 2, PITCH_Y / 2,
                      meta={"period": half, "score": dict(self.score)})
            team = "HAR"
        return self.events


def simulate(seed: int) -> list[Event]:
    return _Sim(seed).run()
