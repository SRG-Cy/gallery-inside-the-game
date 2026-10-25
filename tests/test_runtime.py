import asyncio

import pytest

from gallery.agents.crew import Crew
from gallery.audit import Audit
from gallery.runtime import Conflict, MatchRuntime
from gallery.sim.engine import simulate
from gallery.stats.detectors import Detectors
from gallery.stats.engine import StatsEngine
from tests.fakes import FakeLLM


def make_runtime(llm=None):
    sent = []

    async def broadcast(msg):
        sent.append(msg)

    llm = llm or FakeLLM(default="not json")
    rt = MatchRuntime(lambda stats: Crew(llm, stats), Audit(":memory:"), broadcast)
    return rt, sent


async def step_until(rt, cond, limit=2000):
    for _ in range(limit):
        await rt.step()
        await rt.drain()
        if cond():
            return
    raise AssertionError("condition never met")


def pending(rt):
    return [p for p in rt.proposals.values() if p.status == "pending"]


async def test_full_match_airs_and_audits():
    rt, sent = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    rt.set_auto_approve(True)
    await step_until(rt, lambda: rt.finished)
    await rt.drain()
    aired = [p for p in rt.proposals.values() if p.status == "aired"]
    assert aired
    rows = rt.audit.all(rt.match_id)
    kinds_for = {r["kind"] for r in rows if r["proposal_id"] == aired[0].id}
    assert {"proposed", "approved", "aired"} <= kinds_for
    assert set(rt.recaps) == {"HT", "FT"}
    assert any(m["type"] == "tick" for m in sent)
    assert rt.snapshot()["finished"] is True


async def test_auto_approve_only_low_risk():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    rt.set_auto_approve(True)
    await step_until(rt, lambda: rt.finished)
    statuses = {(p.moment.kind, p.status) for p in rt.proposals.values()}
    assert all(kind == "speed" for kind, status in statuses if status == "aired")
    assert any(kind != "speed" for kind, _ in statuses)


async def test_double_approve_conflict():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    pid = pending(rt)[0].id
    p = await rt.approve(pid)
    assert p.status == "aired" and rt.on_air[-1]["proposal_id"] == pid
    with pytest.raises(Conflict):
        await rt.approve(pid)
    assert sum(a["proposal_id"] == pid for a in rt.on_air) == 1


async def test_approve_expired_conflict():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    p = pending(rt)[0]
    await step_until(rt, lambda: rt.t > p.expires_at)
    assert rt.proposals[p.id].status == "expired"
    with pytest.raises(Conflict):
        await rt.approve(p.id)
    assert any(r["kind"] == "expired" and r["proposal_id"] == p.id for r in rt.audit.all(rt.match_id))


async def test_reject_requires_reason_and_logs_it():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    pid = pending(rt)[0].id
    with pytest.raises(ValueError):
        await rt.reject(pid, "  ")
    await rt.reject(pid, "Not the story right now")
    row = [r for r in rt.audit.all(rt.match_id) if r["kind"] == "rejected"][0]
    assert row["data"]["reason"] == "Not the story right now"


async def test_edit_with_wrong_number_logged_override():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    pid = pending(rt)[0].id
    p = await rt.approve(pid, edited_text="Northgate FC have had 999 shots.")
    shown = p.overlay.body if p.overlay.kind == "lower_third" else p.overlay.title
    assert p.status == "aired" and shown == "Northgate FC have had 999 shots."
    kinds = [r["kind"] for r in rt.audit.all(rt.match_id) if r["proposal_id"] == pid]
    assert "edited" in kinds and "override" in kinds


async def test_approval_personalizes_in_background():
    rt, sent = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    pid = pending(rt)[0].id
    await rt.approve(pid)
    await rt.drain()
    assert set(rt.proposals[pid].variants) == {"casual", "analyst", "player", "es"}
    assert any(m["type"] == "proposal_update" and m["proposal"]["variants"] for m in sent)


async def test_restart_resets_state():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    first = rt.match_id
    await rt.start(seed=8, speed=15, autorun=False)
    assert rt.match_id != first and rt.t == 0 and rt.proposals == {} and rt.on_air == []
    assert rt.stats.events == []


async def test_autorun_loop_and_restart_cancels_previous():
    rt, _ = make_runtime()
    rt.tick_wall = 0
    await rt.start(seed=7, speed=30)
    first_task = rt._loop_task
    await rt.start(seed=7, speed=30)
    assert first_task.cancelled() or first_task.done()
    await rt.stop()


def test_speed_validation():
    rt, _ = make_runtime()
    with pytest.raises(ValueError):
        rt.set_speed(7)
    rt.set_speed(15)
    assert rt.speed == 15


async def test_audit_rows_are_broadcast():
    rt, sent = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    await rt.reject(pending(rt)[0].id, "Too early")
    await rt.drain()
    rows = [m["row"] for m in sent if m["type"] == "audit"]
    assert any(r["kind"] == "rejected" for r in rows)
    assert any(r["kind"] == "proposed" for r in rows)


async def test_shelf_life_gives_producer_twenty_real_seconds_at_any_speed():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: pending(rt))
    p = pending(rt)[0]
    assert p.expires_at - p.moment.t >= 20 * 30


async def test_no_momentum_swing_in_first_ten_minutes():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: rt.t >= 15 * 60)
    await rt.drain()
    assert all(p.moment.t >= 600 for p in rt.proposals.values() if p.moment.kind == "momentum_swing")


async def test_new_proposal_during_expiry_broadcast_does_not_kill_loop():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: len(pending(rt)) >= 2)
    for p in pending(rt):
        p.expires_at = rt.t - 1
    extra = pending(rt)[0].model_copy(update={"id": "late-arrival", "expires_at": rt.t + 999})

    async def broadcast(msg):
        await asyncio.sleep(0)
        rt.proposals.setdefault("late-arrival", extra)
    rt.broadcast = broadcast
    await rt.step()  # must not raise "dictionary changed size during iteration"
    assert rt.proposals["late-arrival"].status == "pending"


async def test_overlapping_starts_leave_one_loop():
    async def yielding(msg):
        await asyncio.sleep(0)
    rt = MatchRuntime(lambda stats: Crew(FakeLLM(default="x"), stats), Audit(":memory:"), yielding)
    rt.tick_wall = 0.01
    await asyncio.gather(rt.start(7, 30), rt.start(7, 30))
    loops = [t for t in asyncio.all_tasks() if t.get_coro().__qualname__ == "MatchRuntime._loop" and not t.done()]
    assert len(loops) == 1
    await rt.stop()
    await asyncio.sleep(0)
    assert not [t for t in asyncio.all_tasks() if t.get_coro().__qualname__ == "MatchRuntime._loop" and not t.done()]


async def test_in_flight_cap_holds_within_one_tick():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    stats = StatsEngine()
    det = Detectors(stats)
    llm_moments = []
    for e in simulate(7):
        stats.ingest(e)
        llm_moments += [m for m in det.check(e) if m.kind in ("big_chance", "tactical_shift")]
        if len(llm_moments) >= 6:
            break
    for m in llm_moments[:6]:
        rt._schedule(m)
    assert rt.in_flight == 3
    assert sum(r["kind"] == "dropped" for r in rt.audit.all(rt.match_id)) == 3
    await rt.drain()
    assert rt.in_flight == 0


async def test_edit_changes_title_for_player_tag():
    rt, _ = make_runtime()
    await rt.start(seed=7, speed=30, autorun=False)
    await step_until(rt, lambda: any(p.overlay.kind == "player_tag" for p in pending(rt)))
    p = next(p for p in pending(rt) if p.overlay.kind == "player_tag")
    await rt.approve(p.id, edited_text="Fastest shot of the half")
    assert rt.on_air[-1]["overlay"]["title"] == "Fastest shot of the half"
