"""Template insights: the safe fallback. Every number comes straight from the moment's stats."""
from gallery.models import Claim, Insight, Moment, Overlay
from gallery.sim.squads import PLAYERS, TEAMS
from gallery.stats.engine import StatsEngine


def _team(code: str | None) -> str:
    return TEAMS.get(code or "", "")


def _short(code: str | None) -> str:
    return _team(code).split()[0] if code else ""


def _name(pid: str | None) -> str:
    return PLAYERS[pid].name if pid in PLAYERS else ""


def _opp(code: str) -> str:
    return "HAR" if code == "NOR" else "NOR"


def insight_for(m: Moment, stats: StatsEngine) -> Insight:
    s, team, pid, name = m.stats, m.team or "", m.player_id or "", _name(m.player_id)
    ev = m.evidence_event_ids
    if m.kind == "goal":
        score = s["score"]
        return Insight(
            headline=f"Goal: {name} scores for {_team(team)}",
            why_it_matters=f"{_team(team)} {score[team]}, {_team(_opp(team))} {score[_opp(team)]}. "
                           f"That is {name}'s shot number {s['player']['shots']} today.",
            claims=[Claim(text="goals", metric="goals", value=score[team], subject=team),
                    Claim(text="shots", metric="shots", value=s["player"]["shots"], subject=pid)],
            evidence_event_ids=ev)
    if m.kind == "big_chance":
        return Insight(
            headline=f"Big chance for {name}",
            why_it_matters=f"A chance worth {s['xg']} expected goals, and it is {s['outcome'].replace('_', ' ')}.",
            claims=[Claim(text="xg", metric="xg", value=s["xg"], subject=pid)],
            evidence_event_ids=ev)
    if m.kind == "speed":
        what = "sprint" if s["action"] == "sprint" else "shot"
        return Insight(
            headline=f"{name}: {s['speed_kmh']} km/h {what}",
            why_it_matters=f"One of the fastest {what}s of the match from {_team(team)}.",
            claims=[Claim(text="speed", metric="speed_kmh", value=s["speed_kmh"], subject=pid)],
            evidence_event_ids=ev)
    if m.kind == "milestone":
        p = s["player"]
        return Insight(
            headline=f"{name}: {s['milestone']} completed passes",
            why_it_matters=f"{p['pass_accuracy_pct']}% accuracy with an average pass of {p['avg_pass_m']} m. "
                           f"{_team(team)} are playing through {name.split()[-1]}.",
            claims=[Claim(text="completed", metric="passes_completed", value=s["milestone"], subject=pid),
                    Claim(text="accuracy", metric="pass_accuracy_pct", value=p["pass_accuracy_pct"], subject=pid)],
            evidence_event_ids=ev)
    if m.kind == "pressing_surge":
        return Insight(
            headline=f"{_team(team)} turn up the press",
            why_it_matters=f"{s['rate_per_min']} pressures a minute over the last five, up from "
                           f"{s['baseline_per_min']} before. {s['high_press_share_pct']}% of them in the "
                           f"opposition half: they want the ball back high up the pitch.",
            claims=[Claim(text="rate", metric="rate_per_min", value=s["rate_per_min"], subject=team),
                    Claim(text="baseline", metric="baseline_per_min", value=s["baseline_per_min"], subject=team)],
            evidence_event_ids=ev)
    if m.kind == "momentum_swing":
        mom = s["momentum"][team]
        return Insight(
            headline=f"Momentum swings to {_team(team)}",
            why_it_matters=f"{_team(team)} now own {mom}% of the attacking momentum, built on shots and "
                           f"entries into the final third. {_team(s['previous_leader'])} have lost control.",
            claims=[Claim(text="momentum", metric="momentum", value=mom, subject=team)],
            evidence_event_ids=ev)
    # tactical_shift
    off = s.get("off") or {}
    off_pid = next((k for k, v in PLAYERS.items() if v.name == off.get("name")), None)
    claims = [Claim(text="passes", metric="passes", value=off["passes"], subject=off_pid)] if off_pid else []
    return Insight(
        headline=f"{_team(team)} change: {name} on",
        why_it_matters=f"{name} replaces {off.get('name', 'a team-mate')}, who leaves after "
                       f"{off.get('passes', 0)} passes. Fresh legs as {_team(team)} chase the game."
        if off_pid else f"{name} comes on for {_team(team)}.",
        claims=claims, evidence_event_ids=ev)


def overlay_for(m: Moment, insight: Insight) -> Overlay:
    kind = {"speed": "player_tag", "milestone": "stat_card"}.get(m.kind, "lower_third")
    stats: list[tuple[str, str]] = []
    if m.kind == "milestone":
        p = m.stats["player"]
        stats = [("Completed passes", str(m.stats["milestone"])),
                 ("Accuracy", f"{p['pass_accuracy_pct']}%"), ("Avg pass", f"{p['avg_pass_m']} m")]
    return Overlay(kind=kind, title=insight.headline, body=insight.why_it_matters, stats=stats,
                   t_start=m.t, duration_s=12 if m.kind == "goal" else 8)


_ES = {
    "goal": "Gol de {name} para {team}.",
    "big_chance": "Gran ocasión para {name}.",
    "speed": "{name}, a {speed} km/h.",
    "milestone": "{name} ya suma {n} pases completados.",
    "pressing_surge": "{team} aprieta arriba: {rate} presiones por minuto.",
    "momentum_swing": "El impulso es ahora de {team}: {mom}% del dominio ofensivo.",
    "tactical_shift": "Cambio en {team}: entra {name}.",
}

_CASUAL = {
    "goal": "Goal! {name} scores for {team}.",
    "big_chance": "So close! {name} nearly scores.",
    "speed": "{name} is flying: {speed} km/h.",
    "milestone": "{name} keeps the ball moving for {team}.",
    "pressing_surge": "{team} are hunting the ball high up the pitch.",
    "momentum_swing": "{team} are on top right now.",
    "tactical_shift": "{team} make a change: {name} comes on.",
}


def variants_for(insight: Insight, m: Moment) -> dict[str, str]:
    s = m.stats
    fields = {
        "name": _name(m.player_id), "team": _team(m.team), "speed": s.get("speed_kmh"),
        "n": s.get("milestone"), "rate": s.get("rate_per_min"),
        "mom": (s.get("momentum") or {}).get(m.team or ""),
    }
    player = s.get("player")
    if m.player_id in PLAYERS and player:
        player_text = (f"Following {player['name']}: {player['passes_completed']} completed passes, "
                       f"{player['pass_accuracy_pct']}% accuracy.")
    else:
        player_text = _CASUAL[m.kind].format(**fields)
    return {
        "casual": _CASUAL[m.kind].format(**fields),
        "analyst": f"{insight.headline}. {insight.why_it_matters}",
        "player": player_text,
        "es": _ES[m.kind].format(**fields),
    }
