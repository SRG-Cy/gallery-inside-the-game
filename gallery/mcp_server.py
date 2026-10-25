"""Read-only MCP server so a broadcaster's own agents can query the live match.

Exposes the same deterministic stats the Analyst agent uses, plus what is on air. Nothing here can
change the match, the queue or the audit trail.
"""
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from gallery.sim.squads import PLAYERS, SQUADS, TEAMS
from gallery.stats.engine import TEAMS as TEAM_CODES

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                            openWorldHint=False)


def make_mcp(runtime) -> MCPServer:
    mcp = MCPServer(
        name="gallery", version="0.1.0",
        instructions="Live statistics for a synthetic football match between Northgate FC (NOR) and "
                     "Harbour Athletic (HAR), as computed by Gallery's deterministic stats engine. "
                     "All data is synthetic. Tools are read-only.")

    def team_code(team: str) -> str:
        if team not in TEAM_CODES:
            raise ValueError(f"team must be one of {list(TEAM_CODES)}")
        return team

    @mcp.tool(annotations=READ_ONLY)
    def get_match_state() -> dict:
        """Score, match clock and both teams' current statistics."""
        snap = runtime.stats.snapshot()
        return {"match_id": runtime.match_id, "minute": int(runtime.t // 60), "t": runtime.t,
                "score": snap["score"], "teams": snap["teams"], "finished": runtime.finished}

    @mcp.tool(annotations=READ_ONLY)
    def get_team_stats(team: str) -> dict:
        """Current statistics for one team: 'NOR' (Northgate FC) or 'HAR' (Harbour Athletic)."""
        return runtime.stats.team(team_code(team))

    @mcp.tool(annotations=READ_ONLY)
    def get_player_stats(player_id: str) -> dict:
        """Current statistics for one player, by id such as 'NOR-6'. Use list_players for ids."""
        if player_id not in PLAYERS:
            raise ValueError(f"unknown player {player_id}; use list_players")
        return runtime.stats.player(player_id)

    @mcp.tool(annotations=READ_ONLY)
    def compare_windows(team: str, minutes: int) -> dict:
        """A team's statistics over the last `minutes` match minutes versus the `minutes` before."""
        stats, code = runtime.stats, team_code(team)
        span = 60 * max(1, min(int(minutes), 45))
        now = stats.now
        return {"last": stats.window(code, now - span, now + 0.001),
                "previous": stats.window(code, now - 2 * span, now - span)}

    @mcp.tool(annotations=READ_ONLY)
    def list_on_air() -> dict:
        """Overlays the producer has put on air, with their timing, newest last."""
        return {"on_air": runtime.on_air}

    @mcp.tool(annotations=READ_ONLY)
    def list_players() -> dict:
        """Both squads with player ids, names and positions."""
        return {code: {"club": TEAMS[code], "players": [p.model_dump() for p in squad]}
                for code, squad in SQUADS.items()}

    return mcp
