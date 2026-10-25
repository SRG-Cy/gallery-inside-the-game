"""Deterministic checks that stand between any generated text and the air.

verify() checks a structured Insight: every claim against the stats engine, names against the
squads, minutes against the clock, evidence ids against the event log. verify_text() checks free
text (producer edits, personalized variants) for names, minutes and numbers that appear nowhere
in the visible stats.
"""
import re

from gallery.models import Insight
from gallery.sim.squads import PLAYERS, TEAMS
from gallery.stats.engine import StatsEngine

MAX_HEADLINE = 70
# Numbers that describe time windows rather than stats.
FREE_NUMBERS = {5.0, 10.0, 45.0, 90.0}

_CAP = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
_NAME_RUN = re.compile(rf"{_CAP}(?:'s|’s)?(?: {_CAP}(?:'s|’s)?)+")
_MINUTE = re.compile(r"\b(\d{1,3})(?:'|’| ?min\b|(?:st|nd|rd|th) minute)")
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")

_STOPWORDS = set("""
The A An And But Or So If In On At Of For From To With Without By Over Under Since After Before
Into Out Up Down Off Back This That These Those Their Them They Its It His Her He She We You
What Why How When Where Who Now Then Just Still Even Only Also Big Huge Goal Goals Chance Press
Pressing Momentum Swing Change Sub Substitution Speed Top Full Half Time Match Game Recap Kick
Analyst Casual Fan Following Watch Look Here There Every Each All Both One Two Three First Second
Last Next Gol Cambio Presión Gran Ocasión Sigue Siguiendo Ahora El La Los Las Un Una De Del En
Con Para Por Al Tras Mientras Entra Sale Minuto Pases Velocidad Impulso Vamos Ojo Qué
""".split())
_ALLOWED = (_STOPWORDS
            | {w for name in TEAMS.values() for w in name.split()}
            | {w for p in PLAYERS.values() for w in p.name.split()})


def _strip_possessive(word: str) -> str:
    return re.sub(r"('s|’s)$", "", word)


def _flatten(d, out: list[float]) -> list[float]:
    if isinstance(d, dict):
        for v in d.values():
            _flatten(v, out)
    elif isinstance(d, (list, tuple)):
        for v in d:
            _flatten(v, out)
    elif isinstance(d, (int, float)) and not isinstance(d, bool):
        out.append(float(d))
    return out


def _dig(facts: dict | None, path: str):
    cur = facts
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _close(claimed: float, actual: float) -> bool:
    tol = 0.5 if float(actual) != int(actual) else 1.0
    return abs(float(claimed) - float(actual)) <= tol


def unknown_names(text: str) -> list[str]:
    bad = []
    for run in _NAME_RUN.findall(text):
        words = [_strip_possessive(w) for w in run.split()]
        for a, b in zip(words, words[1:]):
            if a not in _ALLOWED and b not in _ALLOWED:
                bad.append(f"{a} {b}")
    return bad


def future_minutes(text: str, now: float) -> list[int]:
    limit = int(now // 60) + 1
    return [int(m) for m in _MINUTE.findall(text) if int(m) > limit]


def verify(insight: Insight, stats: StatsEngine, now: float, facts: dict | None = None) -> list[str]:
    errors: list[str] = []
    for c in insight.claims:
        if c.subject in TEAMS:
            source = stats.team(c.subject)
        elif c.subject in PLAYERS:
            source = stats.player(c.subject)
        else:
            errors.append(f"claim '{c.text}': unknown subject {c.subject}")
            continue
        actual = source.get(c.metric, _dig(facts, c.metric))
        if actual is None:
            errors.append(f"claim '{c.text}': no metric {c.metric} for {c.subject}")
        elif isinstance(actual, (int, float)) and isinstance(c.value, (int, float)):
            if not _close(c.value, actual):
                errors.append(f"claim '{c.text}': {c.metric} for {c.subject} is {actual}, not {c.value}")
        elif str(actual).casefold() != str(c.value).casefold():
            errors.append(f"claim '{c.text}': {c.metric} for {c.subject} is {actual}, not {c.value}")
    texts = [insight.headline, insight.why_it_matters] + [c.text for c in insight.claims]
    for text in texts:
        errors += [f"unknown person '{n}'" for n in unknown_names(text)]
        errors += [f"minute {m}' is in the future" for m in future_minutes(text, now)]
    for eid in insight.evidence_event_ids:
        e = stats.by_id.get(eid)
        if e is None or e.t > now:
            errors.append(f"evidence event {eid} does not exist yet")
    if len(insight.headline) > MAX_HEADLINE:
        errors.append(f"headline is {len(insight.headline)} chars, max {MAX_HEADLINE}")
    return errors


def verify_text(text: str, stats: StatsEngine, now: float, facts: dict | None = None) -> list[str]:
    errors = [f"unknown person '{n}'" for n in unknown_names(text)]
    errors += [f"minute {m}' is in the future" for m in future_minutes(text, now)]
    visible = _flatten({t: stats.team(t) for t in TEAMS}, [])
    _flatten(facts or {}, visible)
    for pid, p in PLAYERS.items():
        if p.name.split()[-1] in text:
            _flatten(stats.player(pid), visible)
    minutes = {m for m in _MINUTE.findall(text)}
    for raw in _NUMBER.findall(text):
        n = float(raw)
        if raw in minutes or n in FREE_NUMBERS:
            continue
        if not any(_close(n, v) for v in visible):
            errors.append(f"number {raw} does not match any current stat")
    return errors
