import pytest
from fastapi.testclient import TestClient

from gallery.agents.crew import Crew
from gallery.app import create_app
from gallery.config import Settings
from gallery.sim.engine import simulate
from gallery.stats.detectors import Detectors
from gallery.stats.engine import StatsEngine
from tests.fakes import FakeLLM


def settings(tmp_path):
    return Settings("replay", None, None, None, str(tmp_path / "replay"),
                    str(tmp_path / "audit.db"))


@pytest.fixture
def client(tmp_path):
    app = create_app(settings(tmp_path), llm=FakeLLM(default="not json"))
    with TestClient(app) as c:
        yield c


def inject_proposal(client) -> str:
    """Put one pending proposal in the queue without running the clock."""
    rt = client.app.state.runtime
    stats = StatsEngine()
    det = Detectors(stats)
    for e in simulate(7):
        stats.ingest(e)
        moments = det.check(e)
        if moments:
            p = client.portal.call(Crew(FakeLLM(default="x"), stats).propose, moments[0], e.t)
            rt.stats, rt.t = stats, e.t
            rt.proposals[p.id] = p
            return p.id
    raise AssertionError


def test_ws_snapshot_on_connect(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot" and "proposals" in msg and "teams" in msg


def test_two_clients_get_same_stream(client):
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.receive_json(), b.receive_json()
        assert client.post("/api/match/start", json={"seed": 7, "speed": 30}).status_code == 200

        def first_tick(ws):
            for _ in range(50):
                m = ws.receive_json()
                if m["type"] == "tick":
                    return m
        ta, tb = first_tick(a), first_tick(b)
        assert ta["match_id"] == tb["match_id"]


def test_start_rejects_bad_speed(client):
    assert client.post("/api/match/start", json={"seed": 7, "speed": 7}).status_code == 422


def test_reject_requires_reason(client):
    pid = inject_proposal(client)
    assert client.post(f"/api/proposals/{pid}/reject", json={"reason": " "}).status_code == 422
    assert client.post(f"/api/proposals/{pid}/reject", json={"reason": "Not now"}).status_code == 200


def test_approve_twice_409_and_unknown_404(client):
    pid = inject_proposal(client)
    assert client.post(f"/api/proposals/{pid}/approve", json={}).status_code == 200
    assert client.post(f"/api/proposals/{pid}/approve", json={}).status_code == 409
    assert client.post("/api/proposals/nope/approve", json={}).status_code == 404


def test_overlays_endpoint_shape(client):
    pid = inject_proposal(client)
    client.post(f"/api/proposals/{pid}/approve", json={"text": None})
    items = client.get("/api/overlays").json()
    assert items[-1]["proposal_id"] == pid
    assert set(items[-1]["overlay"]) == {"kind", "title", "body", "stats", "t_start", "duration_s"}


def test_audit_and_snapshot_endpoints(client):
    pid = inject_proposal(client)
    client.post(f"/api/proposals/{pid}/reject", json={"reason": "Off-topic"})
    assert any(r["kind"] == "rejected" for r in client.get("/api/audit").json())
    assert client.get("/api/snapshot").json()["match_id"]


def test_focus_player_and_squads(client):
    squads = client.get("/api/squads").json()
    assert len(squads["NOR"]) == 14
    assert client.post("/api/focus", json={"player_id": "HAR-9"}).status_code == 200
    assert client.post("/api/focus", json={"player_id": "X"}).status_code == 422


def test_events_by_id_only_returns_played_events(client):
    inject_proposal(client)
    rt = client.app.state.runtime
    played = rt.stats.events[-1].id
    got = client.get(f"/api/events?ids=1,2,{played},{played + 500}").json()
    assert [e["id"] for e in got] == [1, 2, played]
    assert client.get("/api/events?ids=abc").status_code == 422
