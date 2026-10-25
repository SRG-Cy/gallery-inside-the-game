from collections import Counter
from itertools import count

from gallery.models import Event
from gallery.sim.engine import simulate
from gallery.stats.detectors import Detectors
from gallery.stats.engine import StatsEngine


class Feed:
    def __init__(self):
        self.stats = StatsEngine()
        self.det = Detectors(self.stats)
        self.ids = count(1)
        self.moments = []

    def add(self, t, type_, team, pid, x=50, y=34, **kw):
        e = Event(id=next(self.ids), t=t, type=type_, team=team, player_id=pid, x=x, y=y, **kw)
        self.stats.ingest(e)
        self.moments += self.det.check(e)
        return e

    def kinds(self):
        return Counter(m.kind for m in self.moments)


def test_goal():
    f = Feed()
    f.add(10, "shot", "NOR", "NOR-11", x=95, y=34, outcome="goal", speed_kmh=80)
    g = f.add(11, "goal", "NOR", "NOR-11", x=105, y=34)
    m = [m for m in f.moments if m.kind == "goal"]
    assert len(m) == 1 and m[0].priority == 3 and g.id in m[0].evidence_event_ids
    assert m[0].player_id == "NOR-11"


def test_big_chance_only_in_box_and_not_goal():
    f = Feed()
    f.add(10, "shot", "NOR", "NOR-11", x=95, y=34, outcome="saved", speed_kmh=70,
          meta={"xg": 0.4})
    f.add(12, "shot", "NOR", "NOR-11", x=95, y=34, outcome="saved", speed_kmh=70,
          meta={"xg": 0.1})
    f.add(20, "shot", "NOR", "NOR-11", x=70, y=34, outcome="saved", speed_kmh=70)
    f.add(30, "shot", "HAR", "HAR-11", x=10, y=30, outcome="off_target", speed_kmh=70,
          meta={"xg": 0.3})
    assert f.kinds()["big_chance"] == 2


def test_speed_thresholds():
    f = Feed()
    f.add(10, "sprint", "NOR", "NOR-9", speed_kmh=32.9)
    f.add(20, "sprint", "NOR", "NOR-9", speed_kmh=33.0)
    f.add(30, "shot", "HAR", "HAR-11", x=40, y=34, outcome="off_target", speed_kmh=104)
    assert f.kinds()["speed"] == 2


def test_milestone_fires_once_at_50():
    f = Feed()
    for i in range(60):
        f.add(10 + i, "pass", "NOR", "NOR-6", x=40, y=34, end_x=45, end_y=34, outcome="complete")
    ms = [m for m in f.moments if m.kind == "milestone"]
    assert len(ms) == 1 and ms[0].stats["milestone"] == 50


def test_pressing_surge_and_cooldown():
    f = Feed()
    for i in range(10):  # 1 pressure per minute for 10 minutes
        f.add(60 * i + 30, "pressure", "NOR", "NOR-7", x=70, y=34)
    for i in range(30):  # then 3 per minute for 10 minutes
        f.add(630 + 20 * i, "pressure", "NOR", "NOR-7", x=70, y=34)
    ms = [m for m in f.moments if m.kind == "pressing_surge"]
    assert len(ms) == 1 and ms[0].team == "NOR" and len(ms[0].evidence_event_ids) <= 10


def test_momentum_swing():
    f = Feed()
    t = 0
    for _ in range(10):
        t += 30
        f.add(t, "shot", "NOR", "NOR-11", x=95, y=34, outcome="saved", speed_kmh=70)
    for _ in range(25):
        t += 30
        f.add(t, "shot", "HAR", "HAR-11", x=10, y=34, outcome="saved", speed_kmh=70)
    ms = [m for m in f.moments if m.kind == "momentum_swing"]
    assert len(ms) == 1 and ms[0].team == "HAR"


def test_tactical_shift_on_sub():
    f = Feed()
    f.add(3700, "substitution", "HAR", "HAR-12", meta={"off": "HAR-8"})
    assert f.kinds()["tactical_shift"] == 1


def test_full_match_has_story():
    stats = StatsEngine()
    det = Detectors(stats)
    kinds = Counter()
    for e in simulate(7):
        stats.ingest(e)
        kinds.update(m.kind for m in det.check(e))
    for k in ("goal", "pressing_surge", "momentum_swing", "milestone"):
        assert kinds[k] >= 1, (k, kinds)
    assert kinds["pressing_surge"] <= 6 and kinds["momentum_swing"] <= 6
