from collections import Counter

from gallery.sim.engine import simulate
from gallery.sim.squads import SQUADS


def test_deterministic():
    assert simulate(7) == simulate(7)


def test_different_seeds_differ():
    assert simulate(7) != simulate(8)


def test_shape():
    events = simulate(7)
    assert 1500 <= len(events) <= 3500
    types = {e.type for e in events}
    for t in ["pass", "shot", "tackle", "pressure", "possession_change", "goal",
              "period_start", "period_end"]:
        assert t in types, t
    assert all(0 <= e.x <= 105 and 0 <= e.y <= 68 for e in events)
    assert all(a.t <= b.t for a, b in zip(events, events[1:]))
    assert [e.id for e in events] == list(range(1, len(events) + 1))


def test_players_exist():
    ids = {p.id for team in SQUADS.values() for p in team}
    events = simulate(7)
    assert all(e.player_id in ids for e in events if e.player_id)


def test_pressing_beat():
    events = simulate(7)
    nor_press = [e for e in events if e.type == "pressure" and e.team == "NOR"]
    avg_per_min = len(nor_press) / 90
    window = [e for e in nor_press if 55 * 60 <= e.t < 63 * 60]
    assert len(window) / 8 >= 1.8 * avg_per_min


def test_story_goals_and_milestone():
    events = simulate(7)
    goals = Counter(e.team for e in events if e.type == "goal")
    assert goals["NOR"] >= 1 and goals["HAR"] >= 1
    completed = Counter(e.player_id for e in events
                        if e.type == "pass" and e.team == "NOR" and e.outcome == "complete")
    assert max(completed.values()) >= 50
