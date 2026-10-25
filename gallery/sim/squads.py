"""Fictional squads. No real clubs or players."""
from gallery.models import Player

TEAMS = {"NOR": "Northgate FC", "HAR": "Harbour Athletic"}

_POSITIONS = ["GK", "RB", "CB", "CB", "LB", "CM", "CM", "AM", "RW", "LW", "ST", "CM", "RW", "ST"]

_NAMES = {
    "NOR": ["Tomas Reyner", "Kofi Adeyemi", "Lars Brandvold", "Mateo Quiroga", "Callum Pryce",
            "Idris Okafor", "Jonah Whitlock", "Elio Marchetti", "Sami Haddad", "Ruben Calloway",
            "Dario Venn", "Theo Marsh", "Yusuf Belkadi", "Aaron Fenwick"],
    "HAR": ["Piotr Lewand", "Nathan Osei", "Bram de Kuyper", "Owen Talbot", "Luca Ferrandi",
            "Malik Sowe", "Hugo Delacroix", "Rory Gallen", "Kenji Arata", "Felix Dunmore",
            "Marco Silvano", "Ewan Strachan", "Nico Varga", "Tariq Lindqvist"],
}


def _squad(team: str) -> list[Player]:
    return [Player(id=f"{team}-{i + 1}", name=n, team=team, number=i + 1, position=_POSITIONS[i])
            for i, n in enumerate(_NAMES[team])]


SQUADS: dict[str, list[Player]] = {t: _squad(t) for t in TEAMS}
PLAYERS: dict[str, Player] = {p.id: p for squad in SQUADS.values() for p in squad}
STARTERS = 11
