import pytest

from gallery.agents import templates
from gallery.agents.verifier import verify, verify_text
from gallery.models import Claim, Insight
from gallery.sim.engine import simulate
from gallery.stats.detectors import Detectors
from gallery.stats.engine import StatsEngine


@pytest.fixture(scope="module")
def first_half():
    s = StatsEngine()
    for e in simulate(7):
        if e.t > 45 * 60:
            break
        s.ingest(e)
    return s


def insight(claims, headline="Northgate on top", why="Okafor is running the game.", ev=None):
    return Insight(headline=headline, why_it_matters=why, claims=claims,
                   evidence_event_ids=ev or [1])


def test_verify_passes_true_claim(first_half):
    acc = first_half.team("NOR")["pass_accuracy_pct"]
    i = insight([Claim(text=f"{acc}% passing", metric="pass_accuracy_pct", value=acc, subject="NOR")])
    assert verify(i, first_half, first_half.now) == []


def test_verify_catches_wrong_number(first_half):
    acc = first_half.team("NOR")["pass_accuracy_pct"]
    i = insight([Claim(text="x", metric="pass_accuracy_pct", value=acc + 9, subject="NOR")])
    errors = verify(i, first_half, first_half.now)
    assert len(errors) == 1 and "pass_accuracy_pct" in errors[0]
    assert str(acc) in errors[0] and str(acc + 9) in errors[0]


def test_verify_catches_unknown_metric_and_subject(first_half):
    i = insight([Claim(text="x", metric="xg_chain", value=3, subject="NOR"),
                 Claim(text="x", metric="passes", value=3, subject="NOR-99")])
    assert len(verify(i, first_half, first_half.now)) == 2


def test_verify_uses_facts(first_half):
    i = insight([Claim(text="x", metric="rate_per_min", value=4.2, subject="NOR")])
    assert verify(i, first_half, first_half.now, facts={"rate_per_min": 4.2}) == []
    assert verify(i, first_half, first_half.now, facts={"rate_per_min": 2.0}) != []


def test_verify_catches_unknown_player(first_half):
    i = insight([], why="Marcus Fields has been everywhere for Northgate FC.")
    errors = verify(i, first_half, first_half.now)
    assert any("Marcus Fields" in e for e in errors)


def test_known_names_and_teams_pass(first_half):
    i = insight([], headline="Idris Okafor drives Northgate FC on",
                why="The Harbour Athletic midfield cannot get near Okafor's passing.")
    assert verify(i, first_half, first_half.now) == []


def test_verify_catches_future_minute(first_half):
    i = insight([], why="Northgate scored in the 80' after a long spell.")
    assert any("80" in e for e in verify(i, first_half, first_half.now))


def test_verify_catches_future_evidence_and_long_headline(first_half):
    i = insight([], headline="x" * 71, ev=[999999])
    assert len(verify(i, first_half, first_half.now)) == 2


def test_verify_text_flags_number_not_in_stats(first_half):
    acc = first_half.team("NOR")["pass_accuracy_pct"]
    assert verify_text(f"Northgate are passing at {acc}%.", first_half, first_half.now) == []
    assert verify_text("Northgate are passing at 999%.", first_half, first_half.now) != []


def test_template_insight_always_verifies():
    s = StatsEngine()
    d = Detectors(s)
    checked = 0
    for e in simulate(7):
        s.ingest(e)
        for m in d.check(e):
            i = templates.insight_for(m, s)
            assert verify(i, s, s.now, facts=m.stats) == [], (m.kind, i)
            o = templates.overlay_for(m, i)
            assert o.t_start == m.t and o.duration_s == (12 if m.kind == "goal" else 8)
            v = templates.variants_for(i, m)
            assert set(v) == {"casual", "analyst", "player", "es"}
            assert all(verify_text(text, s, s.now, facts=m.stats) == [] for text in v.values()), v
            checked += 1
    assert checked > 20


def test_verify_checks_numbers_in_headline_and_why(first_half):
    i = insight([], headline="Northgate have 97 shots", why="They lead 9-0 with 812 passes.")
    errors = verify(i, first_half, first_half.now)
    assert any("97" in e for e in errors) and any("812" in e for e in errors)


def test_single_unknown_name_mid_sentence_is_flagged(first_half):
    i = insight([], why="Northgate keep losing the ball to Messi in midfield.")
    assert any("Messi" in e for e in verify(i, first_half, first_half.now))
    ok = insight([], headline="Goal: Idris Okafor scores", why="So close! Harbour Athletic nearly level.")
    assert verify(ok, first_half, first_half.now) == []


def test_minutes_written_as_words_are_minute_references(first_half):
    now = first_half.now  # 45'
    assert verify_text("Harbour Athletic change shape at 40 minutes.", first_half, now) == []
    assert verify_text("Over the last 15 mins Northgate FC dominate.", first_half, now) == []
    assert any("80" in e for e in verify_text("A big change at 80 minutes.", first_half, now))


def test_stat_labels_are_not_names():
    from gallery.agents.verifier import unknown_names
    assert unknown_names("Shots on target: 3. Pass Accuracy: 84%. Avg Pass Distance: 18 m.") == []
    assert unknown_names("It reflects Northern FC's rhythm.") == ["Northern"]


def test_number_words_are_checked_like_digits(first_half):
    shots = first_half.team("NOR")["shots"]
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
             "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
             "nineteen", "twenty"]
    assert verify_text(f"Northgate FC have taken {words[shots]} shots.", first_half, first_half.now) == []
    assert any("nineteen" in e or "19" in e for e in
               verify_text("Northgate FC have nineteen shots on target and nineteen corners.", first_half,
                           first_half.now)) or first_half.team("NOR")["shots_on_target"] in (18, 19, 20)
