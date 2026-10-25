"""Owns one live match: the clock, detection, the proposal queue, producer actions and the audit."""
import asyncio
import logging
import uuid
from typing import Awaitable, Callable

from gallery.agents.crew import TEMPLATE_ONLY, Crew
from gallery.agents.verifier import verify_text
from gallery.audit import Audit
from gallery.models import Moment, Proposal
from gallery.sim.engine import FULL, HALF, simulate
from gallery.sim.squads import PLAYERS
from gallery.stats.detectors import Detectors
from gallery.stats.engine import StatsEngine

log = logging.getLogger(__name__)

SPEEDS = (1, 15, 30)
TICK_WALL = 0.25
MAX_IN_FLIGHT = 3
AUTO_KINDS = {"speed"}
MIN_SHELF_WALL_S = 20  # a human needs time to read and decide, whatever the playback speed


class Conflict(Exception):
    pass


class MatchRuntime:
    def __init__(self, crew_factory: Callable[[StatsEngine], Crew], audit: Audit,
                 broadcast: Callable[[dict], Awaitable[None]], provider: str = "replay"):
        self.crew_factory = crew_factory
        self.audit = audit
        self.broadcast = broadcast
        self.provider = provider
        self.tick_wall = TICK_WALL
        self.speed = 15
        self.auto_approve = False
        self.focus_player = "NOR-6"
        self._loop_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._start_lock = asyncio.Lock()
        self._reset(seed=7)

    def _reset(self, seed: int) -> None:
        self.seed = seed
        self.match_id = f"m-{seed}-{uuid.uuid4().hex[:6]}"
        self.audit.match_id = self.match_id
        self.events = simulate(seed)
        self.idx = 0
        self.t = 0.0
        self.stats = StatsEngine()
        self.detectors = Detectors(self.stats)
        self.crew = self.crew_factory(self.stats)
        self.proposals: dict[str, Proposal] = {}
        self.on_air: list[dict] = []
        self.recaps: dict[str, str] = {}
        self.in_flight = 0
        self.finished = False

    # --- lifecycle ------------------------------------------------------------------------
    async def start(self, seed: int, speed: int, autorun: bool = True) -> None:
        self.set_speed(speed)
        async with self._start_lock:  # overlapping starts must not leave two loops running
            await self.stop()
            self._reset(seed)
            self._log("match_start", 0, None, {"seed": seed, "speed": speed, "provider": self.provider})
            if autorun:
                self._loop_task = asyncio.create_task(self._loop())
            await self.broadcast({"type": "snapshot", **self.snapshot()})

    async def stop(self) -> None:
        tasks = [t for t in [self._loop_task, *self._tasks] if t and not t.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._loop_task = None
        self._tasks.clear()

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def set_speed(self, speed: int) -> None:
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}")
        self.speed = speed

    def set_auto_approve(self, on: bool) -> None:
        self.auto_approve = bool(on)

    def _log(self, kind: str, t: float, proposal_id: str | None, data: dict) -> dict:
        row = self.audit.log(kind, t, proposal_id, data)
        self._spawn(self.broadcast({"type": "audit", "row": row}))
        return row

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _loop(self) -> None:
        try:
            while not self.finished:
                await asyncio.sleep(self.tick_wall)
                await self.step()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("match loop crashed")

    # --- the clock --------------------------------------------------------------------------
    async def step(self) -> None:
        if self.finished:
            return
        self.t = min(FULL, self.t + TICK_WALL * self.speed)
        while self.idx < len(self.events) and self.events[self.idx].t <= self.t:
            e = self.events[self.idx]
            self.idx += 1
            self.stats.ingest(e)
            for m in self.detectors.check(e):
                self._schedule(m)
        for p in list(self.proposals.values()):  # proposals may arrive while we broadcast
            if p.status == "pending" and self.t > p.expires_at:
                p.status = "expired"
                self._log("expired", self.t, p.id, {})
                await self.broadcast({"type": "proposal_update", "proposal": p.model_dump(mode="json")})
        if self.t >= HALF and "HT" not in self.recaps:
            self.recaps["HT"] = ""
            self._spawn(self._recap("HT"))
        if self.t >= FULL and self.idx >= len(self.events):
            self.finished = True
            self.recaps["FT"] = ""
            self._spawn(self._recap("FT"))
        await self.broadcast({"type": "tick", **self._tick()})

    def _schedule(self, m: Moment) -> None:
        self._log("moment", m.t, None, {"kind": m.kind, "team": m.team, "player_id": m.player_id,
                                             "priority": m.priority})
        uses_llm = m.kind not in TEMPLATE_ONLY
        if uses_llm and self.in_flight >= MAX_IN_FLIGHT and m.priority < 3:
            self._log("dropped", m.t, None, {"kind": m.kind, "reason": "agent crew busy"})
            return
        self.in_flight += uses_llm  # counted now, so a burst within one tick respects the cap
        self._spawn(self._propose(m, uses_llm))

    async def _propose(self, m: Moment, uses_llm: bool) -> None:
        match_id = self.match_id
        try:
            p = await self.crew.propose(m, now=self.t)
        finally:
            self.in_flight -= uses_llm
        if match_id != self.match_id:
            return
        p.expires_at = max(p.expires_at, m.t + MIN_SHELF_WALL_S * self.speed)
        for step in p.trace:
            self._log("agent_step", m.t, p.id, step)
        self.proposals[p.id] = p
        self._log("proposed", self.t, p.id, {"source": p.source, "headline": p.insight.headline,
                                                 "overlay_kind": p.overlay.kind})
        await self.broadcast({"type": "proposal", "proposal": p.model_dump(mode="json")})
        if self.auto_approve and (m.kind in AUTO_KINDS or p.overlay.kind == "player_tag"):
            await self.approve(p.id, auto=True)

    async def _recap(self, period: str) -> None:
        approved = [p for p in self.proposals.values() if p.status == "aired"]
        text = await self.crew.recap(approved, self.stats.snapshot(), period)
        self.recaps[period] = text
        self._log("recap", self.t, None, {"period": period, "text": text})
        await self.broadcast({"type": "recap", "period": period, "text": text})

    # --- producer actions -------------------------------------------------------------------
    def _pending(self, pid: str) -> Proposal:
        p = self.proposals.get(pid)
        if p is None:
            raise KeyError(pid)
        if p.status == "pending" and self.t > p.expires_at:
            p.status = "expired"
            self._log("expired", self.t, p.id, {})
        if p.status != "pending":
            raise Conflict(f"proposal {pid} is {p.status}")
        return p

    async def approve(self, pid: str, edited_text: str | None = None, auto: bool = False) -> Proposal:
        p = self._pending(pid)
        # Edit whichever text the overlay actually shows: the body of a lower third, else the title.
        field = "body" if p.overlay.kind == "lower_third" else "title"
        before = getattr(p.overlay, field)
        if edited_text is not None and edited_text.strip() and edited_text != before:
            self._log("edited", self.t, pid, {"field": field, "before": before, "after": edited_text})
            errors = verify_text(edited_text, self.stats, self.t, facts=p.moment.stats)
            if errors:
                self._log("override", self.t, pid, {"errors": errors})
            setattr(p.overlay, field, edited_text)
        p.status = "approved"
        self._log("approved", self.t, pid, {"by": "auto" if auto else "producer"})
        p.status = "aired"
        p.overlay.t_start = self.t
        item = {"proposal_id": pid, "overlay": p.overlay.model_dump(mode="json"), "aired_at": self.t}
        self.on_air.append(item)
        self._log("aired", self.t, pid, {"overlay": item["overlay"]})
        await self.broadcast({"type": "on_air", "item": item})
        await self.broadcast({"type": "proposal_update", "proposal": p.model_dump(mode="json")})
        self._spawn(self._personalize(p))
        return p

    async def _personalize(self, p: Proposal) -> None:
        match_id = self.match_id
        variants = await self.crew.personalize(p, self.focus_player)
        if match_id != self.match_id:
            return
        p.variants = variants
        self._log("personalized", self.t, p.id, {"focus_player": self.focus_player})
        await self.broadcast({"type": "proposal_update", "proposal": p.model_dump(mode="json")})

    async def reject(self, pid: str, reason: str) -> Proposal:
        if not reason or not reason.strip():
            raise ValueError("a reason is required to reject")
        p = self._pending(pid)
        p.status = "rejected"
        self._log("rejected", self.t, pid, {"reason": reason.strip()})
        await self.broadcast({"type": "proposal_update", "proposal": p.model_dump(mode="json")})
        return p

    def set_focus_player(self, pid: str) -> None:
        if pid not in PLAYERS:
            raise ValueError(f"unknown player {pid}")
        self.focus_player = pid

    # --- views ------------------------------------------------------------------------------
    def _tick(self) -> dict:
        snap = self.stats.snapshot()
        recent = self.stats.events[-8:]
        return {"match_id": self.match_id, "t": self.t, "minute": int(self.t // 60), "speed": self.speed,
                "score": snap["score"], "teams": snap["teams"], "finished": self.finished,
                "provider": self.provider, "provider_status": self.crew.llm.status,
                "recent_events": [e.model_dump(mode="json") | {
                    "player_name": PLAYERS[e.player_id].name if e.player_id in PLAYERS else None}
                    for e in recent]}

    def snapshot(self) -> dict:
        props = sorted(self.proposals.values(), key=lambda p: p.moment.t, reverse=True)[:60]
        return {**self._tick(), "seed": self.seed, "auto_approve": self.auto_approve,
                "focus_player": self.focus_player,
                "proposals": [p.model_dump(mode="json") for p in props],
                "on_air": self.on_air[-12:], "recaps": self.recaps,
                "audit": self.audit.all(self.match_id)[-80:]}
