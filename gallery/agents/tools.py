"""Read-only stats tools the Analyst agent can call."""
from typing import Callable

from gallery.stats.engine import StatsEngine


def make_tools(stats: StatsEngine) -> list[Callable]:
    def get_team_stats(team: str) -> dict:
        """Current match statistics for a team. team is 'NOR' (Northgate FC) or 'HAR' (Harbour Athletic)."""
        return stats.team(team)

    def get_player_stats(player_id: str) -> dict:
        """Current match statistics for one player, by id such as 'NOR-6'."""
        return stats.player(player_id)

    def compare_windows(team: str, minutes: int) -> dict:
        """A team's statistics over the last `minutes` match minutes versus the `minutes` before that."""
        now = stats.now
        span = 60 * max(1, min(int(minutes), 45))
        return {"last": stats.window(team, now - span, now + 0.001),
                "previous": stats.window(team, now - 2 * span, now - span)}

    return [get_team_stats, get_player_stats, compare_windows]
