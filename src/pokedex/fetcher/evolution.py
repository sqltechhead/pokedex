"""Turn PokéAPI evolution chains into :class:`EvolutionChain` records."""

from pokedex.fetcher.api import ChainLink, EvolutionChainResponse, EvolutionDetail
from pokedex.models import Evolution, EvolutionChain

# Species slugs whose display name is not just the slug title-cased.
SPECIAL_NAMES = {
    "mr-mime": "Mr. Mime",
    "mime-jr": "Mime Jr.",
    "mr-rime": "Mr. Rime",
    "farfetchd": "Farfetch’d",
    "sirfetchd": "Sirfetch’d",
    "nidoran-f": "Nidoran♀",
    "nidoran-m": "Nidoran♂",
    "type-null": "Type: Null",
    "ho-oh": "Ho-Oh",
    "porygon-z": "Porygon-Z",
    "jangmo-o": "Jangmo-o",
    "hakamo-o": "Hakamo-o",
    "kommo-o": "Kommo-o",
    "flabebe": "Flabébé",
}

# Item slugs that lose punctuation when title-cased.
SPECIAL_ITEMS = {"kings-rock": "King’s Rock"}

RELATIVE_STATS = {1: "Atk > Def", -1: "Atk < Def", 0: "Atk = Def"}


def display_name(slug: str) -> str:
    """``"mr-mime"`` -> ``"Mr. Mime"``; used for species not in the database."""
    return SPECIAL_NAMES.get(slug) or slug.replace("-", " ").title()


def pretty(slug: str) -> str:
    """``"thunder-stone"`` -> ``"Thunder Stone"``."""
    return SPECIAL_ITEMS.get(slug) or slug.replace("-", " ").title()


def build_chain(response: EvolutionChainResponse) -> EvolutionChain:
    """Flatten the nested chain into steps, parents before children."""
    evolutions: list[Evolution] = []
    pending: list[ChainLink] = [response.chain]
    while pending:
        link = pending.pop(0)
        for child in link.evolves_to:
            evolutions.append(
                Evolution(
                    from_id=link.species.id,
                    to_id=child.species.id,
                    to_name=display_name(child.species.name),
                    method=describe(child.evolution_details),
                )
            )
            pending.append(child)
    root = response.chain.species
    return EvolutionChain(
        id=response.id,
        root_id=root.id,
        root_name=display_name(root.name),
        evolutions=tuple(evolutions),
    )


def describe(details: list[EvolutionDetail]) -> str:
    """A short label for the arrow, e.g. "Lv. 16", "Fire Stone", "Trade holding Metal Coat".

    PokéAPI lists one detail per game where the method differs (Leafeon has six);
    the one marked is_default is the current method.
    """
    if not details:
        return ""
    detail = next((d for d in details if d.is_default), details[0])
    return describe_detail(detail)


def describe_detail(d: EvolutionDetail) -> str:
    trigger = d.trigger.name if d.trigger else ""
    conditions: list[str] = []

    if trigger == "use-item" and d.item:
        base = pretty(d.item.name)
    elif trigger == "trade":
        base = "Trade"
        if d.held_item:
            base += f" holding {pretty(d.held_item.name)}"
        if d.trade_species:
            base += f" for {display_name(d.trade_species.name)}"
    elif trigger == "level-up":
        if d.min_level:
            base = f"Lv. {d.min_level}"
        elif d.min_happiness:
            base = "High friendship"
        elif d.min_affection:
            base = "High affection"
        elif d.min_beauty:
            base = "High beauty"
        else:
            base = "Level up"
        if d.min_level and d.min_happiness:
            conditions.append("friendship")
    elif trigger == "use-move" and d.used_move:
        base = f"Use {pretty(d.used_move.name)}"
        if d.min_move_count:
            base += f" {d.min_move_count}×"
    else:
        base = pretty(trigger) if trigger else "Special"

    if trigger != "trade" and d.held_item:
        conditions.append(f"holding {pretty(d.held_item.name)}")
    if d.known_move:
        conditions.append(f"knowing {pretty(d.known_move.name)}")
    if d.known_move_type:
        conditions.append(f"knowing a {pretty(d.known_move_type.name)} move")
    if d.party_species:
        conditions.append(f"with {display_name(d.party_species.name)}")
    if d.party_type:
        conditions.append(f"with a {pretty(d.party_type.name)} type")
    if d.location:
        conditions.append(f"at {pretty(d.location.name)}")
    if d.relative_physical_stats in RELATIVE_STATS:
        conditions.append(RELATIVE_STATS[d.relative_physical_stats])
    if d.gender == 1:
        conditions.append("female")
    elif d.gender == 2:
        conditions.append("male")
    if d.time_of_day:
        conditions.append(d.time_of_day)
    if d.needs_overworld_rain:
        conditions.append("in rain")
    if d.turn_upside_down:
        conditions.append("upside down")

    return ", ".join([base, *conditions])
