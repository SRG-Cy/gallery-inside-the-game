"""HTTP + WebSocket API for the producer console and downstream graphics systems."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gallery.agents.crew import Crew
from gallery.audit import Audit
from gallery.config import Settings, load_settings
from gallery.llm import LLM, make_llm
from gallery.runtime import SPEEDS, Conflict, MatchRuntime
from gallery.sim.squads import SQUADS

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class StartBody(BaseModel):
    seed: int = 7
    speed: int = 15


class SpeedBody(BaseModel):
    speed: int


class ApproveBody(BaseModel):
    text: str | None = None


class RejectBody(BaseModel):
    reason: str = ""


class ToggleBody(BaseModel):
    on: bool


class FocusBody(BaseModel):
    player_id: str


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                self.clients.discard(ws)


def create_app(settings: Settings | None = None, llm: LLM | None = None) -> FastAPI:
    settings = settings or load_settings()
    llm = llm or make_llm(settings)
    hub = Hub()
    runtime = MatchRuntime(lambda stats: Crew(llm, stats), Audit(settings.db_path), hub.broadcast,
                           provider=settings.provider)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await runtime.stop()

    app = FastAPI(title="Gallery", lifespan=lifespan)
    app.state.runtime = runtime

    def check_speed(speed: int) -> None:
        if speed not in SPEEDS:
            raise HTTPException(422, f"speed must be one of {list(SPEEDS)}")

    @app.post("/api/match/start")
    async def start(body: StartBody):
        check_speed(body.speed)
        await runtime.start(body.seed, body.speed)
        return {"match_id": runtime.match_id}

    @app.post("/api/match/speed")
    async def speed(body: SpeedBody):
        check_speed(body.speed)
        runtime.set_speed(body.speed)
        return {"speed": runtime.speed}

    async def act(coro_fn, *args):
        try:
            p = await coro_fn(*args)
        except KeyError:
            raise HTTPException(404, "unknown proposal")
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return p.model_dump(mode="json")

    @app.post("/api/proposals/{pid}/approve")
    async def approve(pid: str, body: ApproveBody):
        return await act(runtime.approve, pid, body.text)

    @app.post("/api/proposals/{pid}/reject")
    async def reject(pid: str, body: RejectBody):
        return await act(runtime.reject, pid, body.reason)

    @app.post("/api/auto_approve")
    async def auto_approve(body: ToggleBody):
        runtime.set_auto_approve(body.on)
        return {"auto_approve": runtime.auto_approve}

    @app.post("/api/focus")
    async def focus(body: FocusBody):
        try:
            runtime.set_focus_player(body.player_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"focus_player": runtime.focus_player}

    @app.get("/api/squads")
    async def squads():
        return {t: [p.model_dump() for p in players] for t, players in SQUADS.items()}

    @app.get("/api/snapshot")
    async def snapshot():
        return runtime.snapshot()

    @app.get("/api/overlays")
    async def overlays():
        """Aired overlays with timing, for a downstream graphics renderer."""
        return runtime.on_air

    @app.get("/api/audit")
    async def audit():
        return runtime.audit.all(runtime.match_id)

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        await socket.send_json({"type": "snapshot", **runtime.snapshot()})
        hub.clients.add(socket)
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            hub.clients.discard(socket)

    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app

