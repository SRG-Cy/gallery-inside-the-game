import json

from fastapi.testclient import TestClient

from gallery.app import create_app
from gallery.config import Settings
from gallery.mcp_server import make_mcp
from tests.fakes import FakeLLM
from tests.test_api import inject_proposal

EXPECTED_TOOLS = {"get_match_state", "get_team_stats", "get_player_stats", "compare_windows",
                  "list_on_air", "list_players"}


def make_client(tmp_path):
    s = Settings("replay", None, None, None, str(tmp_path / "r"), str(tmp_path / "a.db"))
    return TestClient(create_app(s, llm=FakeLLM(default="not json")))


def rpc(client, method, params=None, id_=1):
    res = client.post("/mcp", headers={"accept": "application/json, text/event-stream",
                                       "content-type": "application/json"},
                      json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    assert res.status_code == 200, res.text
    return res.json()


def init(client):
    return rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "0"}})


async def test_tools_are_read_only(tmp_path):
    with make_client(tmp_path) as client:
        tools = await make_mcp(client.app.state.runtime).list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_mcp_over_http_lists_tools(tmp_path):
    with make_client(tmp_path) as client:
        assert init(client)["result"]["serverInfo"]["name"] == "gallery"
        names = {t["name"] for t in rpc(client, "tools/list", id_=2)["result"]["tools"]}
    assert names == EXPECTED_TOOLS


def test_mcp_team_stats_match_the_live_engine(tmp_path):
    with make_client(tmp_path) as client:
        inject_proposal(client)
        rt = client.app.state.runtime
        init(client)
        out = rpc(client, "tools/call", {"name": "get_team_stats", "arguments": {"team": "NOR"}}, id_=3)
        data = json.loads(out["result"]["content"][0]["text"])
    assert data == rt.stats.team("NOR")


def test_mcp_rejects_unknown_player(tmp_path):
    with make_client(tmp_path) as client:
        init(client)
        out = rpc(client, "tools/call", {"name": "get_player_stats", "arguments": {"player_id": "NOR-99"}}, id_=4)
    assert out["result"]["isError"] is True


def test_mcp_lists_aired_overlays(tmp_path):
    with make_client(tmp_path) as client:
        pid = inject_proposal(client)
        client.post(f"/api/proposals/{pid}/approve", json={})
        init(client)
        out = rpc(client, "tools/call", {"name": "list_on_air", "arguments": {}}, id_=5)
        items = json.loads(out["result"]["content"][0]["text"])
    assert items["on_air"][-1]["proposal_id"] == pid
