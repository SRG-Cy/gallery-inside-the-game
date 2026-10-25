"""Read-only stats tools the Analyst agent can call."""
import re
from typing import Callable

from gallery.stats.engine import TEAMS, StatsEngine

_WINDOW_METRIC = re.compile(r"^windows\.(NOR|HAR)_(\d{1,2})\.")


def window_facts(stats: StatsEngine, team: str, minutes: int) -> dict:
    """A team's stats over the last `minutes` match minutes and the `minutes` before. Deterministic,
    so the verifier can recompute exactly what the tool returned, even when a reply is replayed."""
    mins = max(1, min(int(minutes), 45))
    now = stats.now
    return {"last": stats.window(team, now - 60 * mins, now + 0.001),
            "previous": stats.window(team, now - 120 * mins, now - 60 * mins)}


def windows_for_claims(stats: StatsEngine, metrics: list[str]) -> dict:
    """The window facts that a set of claim metrics such as "windows.NOR_5.last.pressures" refer to."""
    out = {}
    for metric in metrics:
        m = _WINDOW_METRIC.match(metric)
        if m and m.group(1) in TEAMS:
            out[f"{m.group(1)}_{m.group(2)}"] = window_facts(stats, m.group(1), int(m.group(2)))
    return out


def make_tools(stats: StatsEngine) -> list[Callable]:
    def get_team_stats(team: str) -> dict:
        """Current match statistics for a team. team is 'NOR' (Northgate FC) or 'HAR' (Harbour Athletic)."""
        return stats.team(team)

    def get_player_stats(player_id: str) -> dict:
        """Current match statistics for one player, by id such as 'NOR-6'."""
        return stats.player(player_id)

    def compare_windows(team: str, minutes: int) -> dict:
        """A team's statistics over the last `minutes` match minutes versus the `minutes` before that.
        Cite these figures in claims as metric "<metric_prefix>.last.<key>" or "<metric_prefix>.previous.<key>"."""
        mins = max(1, min(int(minutes), 45))
        return {"metric_prefix": f"windows.{team}_{mins}", **window_facts(stats, team, mins)}

    return [get_team_stats, get_player_stats, compare_windows]
