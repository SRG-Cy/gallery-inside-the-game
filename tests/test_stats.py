from gallery.models import Event
from gallery.sim.engine import simulate
from gallery.stats.engine import StatsEngine


def ev(i, t, type_, team, pid, x=50, y=34, **kw):
    return Event(id=i, t=t, type=type_, team=team, player_id=pid, x=x, y=y, **kw)


def fixture() -> StatsEngine:
    s = StatsEngine()
    for e in [
        ev(1, 0, "period_start", "", None),
        ev(2, 2, "pass", "NOR", "NOR-6", x=50, y=34, end_x=70, end_y=34, outcome="complete"),
        ev(3, 6, "pass", "NOR", "NOR-6", x=60, y=20, end_x=60, end_y=40, outcome="complete",
           under_pressure=True),
        ev(4, 10, "pass", "NOR", "NOR-7", x=60, y=40, end_x=65, end_y=40, outcome="complete"),
        ev(5, 14, "sprint", "NOR", "NOR-9", speed_kmh=33.4, meta={"distance_m": 30}),
        ev(6, 20, "pass", "NOR", "NOR-6", x=65, y=40, end_x=95, end_y=40, outcome="incomplete"),
        ev(7, 30, "possession_change", "HAR", "HAR-6", x=95, y=40),
        ev(8, 35, "pressure", "NOR", "NOR-9", x=80, y=40),
        ev(9, 40, "pass", "HAR", "HAR-6", x=90, y=40, end_x=80, end_y=40, outcome="complete"),
    ]:
        s.ingest(e)
    return s


def test_pass_accuracy():
    assert fixture().team("NOR")["pass_accuracy_pct"] == 75


def test_pass_difficulty():
    # 20 m pass under pressure with no forward progression: 1 + 20/8 + 2 = 5.5
    s = fixture()
    p = s.player("NOR-6")
    assert p["passes"] == 3 and p["passes_completed"] == 2
    assert s.pass_difficulty(s.events[2]) == 5.5


def test_possession_split():
    # NOR in possession 2 -> 30, HAR 30 -> 40.
    t = fixture()
    assert t.team("NOR")["possession_pct"] == 74
    assert t.team("HAR")["possession_pct"] == 26


def test_player_top_speed():
    assert fixture().player("NOR-9")["top_speed_kmh"] == 33.4


def test_pressures_in_opp_half():
    assert fixture().team("NOR")["pressures"] == 1


def test_window_excludes_outside_events():
    w = fixture().window("NOR", 0, 9)
    assert w["passes"] == 2 and w["pass_accuracy_pct"] == 100


def test_full_match_ranges():
    s = StatsEngine()
    for e in simulate(7):
        s.ingest(e)
    snap = s.snapshot()
    nor, har = snap["teams"]["NOR"], snap["teams"]["HAR"]
    assert nor["possession_pct"] + har["possession_pct"] in (99, 100, 101)
    assert nor["momentum"] + har["momentum"] in (99, 100, 101)
    for t in (nor, har):
        assert 0 <= t["control_chaos"] <= 100
        assert 50 <= t["pass_accuracy_pct"] <= 95
    assert snap["score"] == {"NOR": nor["goals"], "HAR": har["goals"]}
