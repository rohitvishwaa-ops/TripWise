"""Deterministic automatic trip planner (no AI).

Pipeline for one city:
  1. fetch real candidate places per interest from Geoapify (via places.fetch_places)
  2. drop unnamed places and duplicates
  3. pick places round-robin across interests (provider proximity order)
  4. split them into days of nearby places (capacity-limited clustering)
  5. order each day by nearest neighbour and label Morning/Afternoon/Evening

Everything after step 1 is pure and deterministic, so the same candidates
always produce the same plan. The planner never invents places, times,
opening hours, prices or travel durations.
"""

import asyncio
import math
import unicodedata
from dataclasses import dataclass, field

import httpx

from places import Place, fetch_places

# Geoapify categories per interest (all verified against the live API).
INTEREST_CATEGORIES: dict[str, list[str]] = {
    # tourism.attraction is left out on purpose: near city centres it is mostly
    # small public artworks and plaques, which crowd out museums and venues.
    "culture": ["entertainment.museum", "entertainment.culture"],
    "history": ["tourism.sights", "heritage"],
    "nature": ["leisure.park", "natural"],
    "food": ["catering.restaurant", "catering.cafe"],
    "shopping": ["commercial.shopping_mall", "commercial.marketplace", "commercial.department_store"],
    "nightlife": ["catering.bar", "catering.pub", "adult.nightclub"],
    "beaches": ["beach"],
    "entertainment": [
        "entertainment.zoo",
        "entertainment.aquarium",
        "entertainment.theme_park",
        "entertainment.cinema",
        "entertainment.planetarium",
    ],
}
# Used when the traveller picks no interests: a general sightseeing mix.
DEFAULT_INTEREST = "sightseeing"
DEFAULT_CATEGORIES = ["tourism.sights", "tourism.attraction", "entertainment.museum", "leisure.park"]

INTEREST_LABELS = {
    "culture": "Culture",
    "history": "History",
    "nature": "Nature",
    "food": "Food",
    "shopping": "Shopping",
    "nightlife": "Nightlife",
    "beaches": "Beaches",
    "entertainment": "Entertainment",
    DEFAULT_INTEREST: "Sightseeing",
}

PACE_PER_DAY = {"relaxed": 2, "balanced": 3, "packed": 5}
SLOTS = ("morning", "afternoon", "evening")

SEARCH_RADII_M = (10_000, 25_000)  # widen once if too few places nearby
MAX_LIMIT_PER_INTEREST = 100


class InsufficientPlacesError(Exception):
    """Too few real places to give every day at least one activity."""

    def __init__(self, found: int, needed: int):
        super().__init__(f"found {found} places, need at least {needed}")
        self.found = found
        self.needed = needed


@dataclass(frozen=True)
class Candidate:
    place: Place
    interest: str

    @property
    def lat(self) -> float:
        return self.place.latitude

    @property
    def lon(self) -> float:
        return self.place.longitude


@dataclass
class PlannedActivity:
    candidate: Candidate
    slot: str


@dataclass
class PlannedDay:
    theme: str | None
    activities: list[PlannedActivity] = field(default_factory=list)


@dataclass
class Plan:
    days: list[PlannedDay]
    warnings: list[str] = field(default_factory=list)
    source: str = "auto"  # "auto" (deterministic) or "ai" (AI-selected, validated)


# --- Interests and pace -----------------------------------------------------


def interest_queries(interests: list[str]) -> list[tuple[str, str]]:
    """(interest, comma-separated categories) per interest, in the user's order."""
    chosen = list(dict.fromkeys(i for i in interests if i in INTEREST_CATEGORIES))
    if not chosen:
        return [(DEFAULT_INTEREST, ",".join(DEFAULT_CATEGORIES))]
    return [(i, ",".join(INTEREST_CATEGORIES[i])) for i in chosen]


def activities_per_day(pace: str) -> int:
    return PACE_PER_DAY[pace]


# --- Geometry ---------------------------------------------------------------


def distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Great-circle (straight-line) distance; not a travel distance or time."""
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _dist(a: Candidate, lat: float, lon: float) -> float:
    return distance_km(a.lat, a.lon, lat, lon)


def _centroid(items: list[Candidate]) -> tuple[float, float]:
    return (
        sum(c.lat for c in items) / len(items),
        sum(c.lon for c in items) / len(items),
    )


# --- Cleaning and selection -------------------------------------------------


def _name_key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", " ".join(name.split())).casefold()
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Drop unnamed places, repeated place IDs and the same name at (almost)
    the same spot (Geoapify can return one venue under several IDs)."""
    seen_ids: set[str] = set()
    seen_named_spots: set[tuple[str, float, float]] = set()
    result = []
    for c in candidates:
        name = (c.place.name or "").strip()
        if not name:
            continue
        spot = (_name_key(name), round(c.lat, 3), round(c.lon, 3))
        if (c.place.id and c.place.id in seen_ids) or spot in seen_named_spots:
            continue
        if c.place.id:
            seen_ids.add(c.place.id)
        seen_named_spots.add(spot)
        result.append(c)
    return result


MIN_SPACING_KM = 0.15  # avoid e.g. three plaques on the same square


def select_balanced(groups: list[list[Candidate]], count: int) -> list[Candidate]:
    """Take one place from each interest in turn so no single interest crowds
    out the others. Each group is already in proximity order. Places within
    MIN_SPACING_KM of an already chosen place are only used if nothing else is
    left, so a day isn't three spots on the same square."""
    picked: list[Candidate] = []
    skipped: list[Candidate] = []
    iters = [iter(g) for g in groups]
    while len(picked) < count and iters:
        still_going = []
        for it in iters:
            if len(picked) >= count:
                break
            item = next(it, None)
            while item is not None and any(_dist(item, p.lat, p.lon) < MIN_SPACING_KM for p in picked):
                skipped.append(item)
                item = next(it, None)
            if item is not None:
                picked.append(item)
                still_going.append(it)
        iters = still_going
    return picked + skipped[: count - len(picked)]


# --- Day allocation ---------------------------------------------------------


def day_capacities(total: int, num_days: int, per_day: int) -> list[int]:
    """Spread `total` places over `num_days` as evenly as possible (max per_day)."""
    total = min(total, num_days * per_day)
    base, extra = divmod(total, num_days)
    return [base + (1 if i < extra else 0) for i in range(num_days)]


def _farthest_first_seeds(items: list[Candidate], k: int, center: tuple[float, float]) -> list[tuple[float, float]]:
    first = min(items, key=lambda c: (_dist(c, *center), c.place.id or ""))
    seeds = [(first.lat, first.lon)]
    while len(seeds) < k:
        nxt = max(
            items,
            key=lambda c: (min(_dist(c, *s) for s in seeds), c.place.id or ""),
        )
        seeds.append((nxt.lat, nxt.lon))
    return seeds


def _assign(items: list[Candidate], centers: list[tuple[float, float]], caps: list[int]) -> list[list[Candidate]]:
    """Capacity-limited assignment: closest (place, day) pairs first."""
    pairs = sorted(
        ((_dist(c, *centers[d]), i, d) for i, c in enumerate(items) for d in range(len(centers))),
    )
    groups: list[list[Candidate]] = [[] for _ in centers]
    done: set[int] = set()
    for _, i, d in pairs:
        if i in done or len(groups[d]) >= caps[d]:
            continue
        groups[d].append(items[i])
        done.add(i)
    return groups


def group_by_proximity(
    items: list[Candidate], num_days: int, caps: list[int], center: tuple[float, float], rounds: int = 5
) -> list[list[Candidate]]:
    """Split places into days so each day's places are close together
    (capacity-constrained k-means with deterministic farthest-first seeds)."""
    if not items:
        return [[] for _ in range(num_days)]
    k = min(num_days, len(items))
    centers = _farthest_first_seeds(items, k, center)
    centers += [centers[-1]] * (num_days - k)
    groups = _assign(items, centers, caps)
    for _ in range(rounds):
        new_centers = [_centroid(g) if g else centers[d] for d, g in enumerate(groups)]
        if new_centers == centers:
            break
        centers = new_centers
        groups = _assign(items, centers, caps)
    # Day 1 starts nearest the city centre; later days move outwards.
    groups.sort(key=lambda g: _dist_to_center(g, center))
    return groups


def _dist_to_center(group: list[Candidate], center: tuple[float, float]) -> float:
    if not group:
        return math.inf
    lat, lon = _centroid(group)
    return distance_km(lat, lon, *center)


# --- Ordering and labels ----------------------------------------------------


def order_nearest_neighbour(items: list[Candidate], start: tuple[float, float]) -> list[Candidate]:
    """Visit the closest remaining place each time, starting near `start`."""
    remaining = list(items)
    ordered: list[Candidate] = []
    here = start
    while remaining:
        nxt = min(remaining, key=lambda c: (_dist(c, *here), c.place.id or ""))
        ordered.append(nxt)
        remaining.remove(nxt)
        here = (nxt.lat, nxt.lon)
    return ordered


def slot_labels(count: int) -> list[str]:
    """Spread a day's activities over Morning/Afternoon/Evening in order."""
    if count <= 0:
        return []
    return [SLOTS[min(2, (i * 3) // count)] for i in range(count)]


def day_theme(items: list[Candidate], interest_order: list[str] | None = None) -> str | None:
    """E.g. "Culture and Food", listed in the traveller's interest order."""
    present = list(dict.fromkeys(c.interest for c in items))
    if interest_order:
        rank = {name: i for i, name in enumerate(interest_order)}
        present.sort(key=lambda name: rank.get(name, len(rank)))
    labels = [INTEREST_LABELS.get(i, i.title()) for i in present]
    if not labels:
        return None
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


# --- Planning ---------------------------------------------------------------


def clean_groups(groups: list[list[Candidate]]) -> tuple[list[Candidate], list[list[Candidate]]]:
    """Deduplicate across all interests; keep each place only at its first
    appearance, so a place listed under two interests is never used twice."""
    unique = dedupe([c for g in groups for c in g])
    available = {id(c) for c in unique}
    cleaned = []
    for g in groups:
        kept = [c for c in g if id(c) in available]
        available.difference_update(id(c) for c in kept)
        cleaned.append(kept)
    return unique, cleaned


def trip_pool(groups: list[list[Candidate]], size: int) -> list[Candidate]:
    """Clean, interest-balanced, spaced-out candidates (e.g. for the AI layer)."""
    _, cleaned = clean_groups(groups)
    return select_balanced(cleaned, size)


def build_plan(
    groups: list[list[Candidate]],
    center: tuple[float, float],
    num_days: int,
    pace: str,
) -> Plan:
    """Pure planning step. `groups` = candidates per interest, proximity order."""
    per_day = activities_per_day(pace)
    needed = num_days * per_day
    unique, cleaned_groups = clean_groups(groups)

    if len(unique) < num_days:
        raise InsufficientPlacesError(found=len(unique), needed=num_days)

    interest_order = [g[0].interest for g in groups if g]
    selected = select_balanced(cleaned_groups, needed)
    caps = day_capacities(len(selected), num_days, per_day)
    day_groups = group_by_proximity(selected, num_days, caps, center)

    days = []
    for group in day_groups:
        ordered = order_nearest_neighbour(group, center)
        slots = slot_labels(len(ordered))
        days.append(
            PlannedDay(
                theme=day_theme(ordered, interest_order),
                activities=[PlannedActivity(c, s) for c, s in zip(ordered, slots)],
            )
        )

    warnings = []
    if len(selected) < needed:
        warnings.append(
            f"Only {len(selected)} matching places were found nearby, so some days "
            f"have fewer than {per_day} activities."
        )
    return Plan(days=days, warnings=warnings)


async def fetch_candidates(
    client: httpx.AsyncClient,
    api_key: str,
    center: tuple[float, float],
    interests: list[str],
    needed: int,
) -> list[list[Candidate]]:
    """Real places per interest (one Geoapify request each, run concurrently).
    Widens the search radius once if there are too few named places."""
    queries = interest_queries(interests)
    limit = min(MAX_LIMIT_PER_INTEREST, max(20, needed * 2))
    groups: list[list[Candidate]] = []
    for radius in SEARCH_RADII_M:
        results = await asyncio.gather(
            *(
                fetch_places(
                    client,
                    api_key,
                    latitude=center[0],
                    longitude=center[1],
                    radius=radius,
                    categories=categories,
                    limit=limit,
                )
                for _, categories in queries
            )
        )
        groups = [[Candidate(p, interest) for p in places] for (interest, _), places in zip(queries, results)]
        if len(dedupe([c for g in groups for c in g])) >= needed:
            break
    return groups


# --- Single-day regeneration --------------------------------------------------


def place_keys(place_id: str | None, name: str | None, lat: float | None, lon: float | None) -> set:
    """Identity keys used to recognise "the same place" across sources."""
    keys: set = set()
    if place_id:
        keys.add(("id", place_id))
    if name and name.strip() and lat is not None and lon is not None:
        keys.add(("spot", _name_key(name), round(lat, 3), round(lon, 3)))
    return keys


def _candidate_keys(c: Candidate) -> set:
    return place_keys(c.place.id, c.place.name, c.lat, c.lon)


def build_day(
    groups: list[list[Candidate]],
    anchor: tuple[float, float],
    pace: str,
    exclude: set,
    avoid: set,
    interest_order: list[str] | None = None,
) -> tuple[PlannedDay, list[str]]:
    """Plan ONE day near `anchor`.

    exclude: keys of places scheduled on other days (never used).
    avoid:   keys of places currently on this day (used only if nothing else
             is available, so regenerating gives fresh suggestions).
    Returns the day and any warnings. Raises InsufficientPlacesError if no
    usable place is left.
    """
    per_day = activities_per_day(pace)
    unique = dedupe([c for g in groups for c in g])
    allowed = [c for c in unique if not (_candidate_keys(c) & exclude)]
    allowed_ids = {id(c) for c in allowed}

    def by_anchor(items: list[Candidate]) -> list[Candidate]:
        return sorted(items, key=lambda c: (_dist(c, *anchor), c.place.id or ""))

    fresh_groups, stale = [], []
    for g in groups:
        kept = [c for c in g if id(c) in allowed_ids]
        allowed_ids.difference_update(id(c) for c in kept)
        fresh_groups.append(by_anchor([c for c in kept if not (_candidate_keys(c) & avoid)]))
        stale.extend(c for c in kept if _candidate_keys(c) & avoid)

    selected = select_balanced(fresh_groups, per_day)
    if len(selected) < per_day:
        selected += by_anchor(stale)[: per_day - len(selected)]
    if not selected:
        raise InsufficientPlacesError(found=0, needed=1)

    ordered = order_nearest_neighbour(selected, anchor)
    day = PlannedDay(
        theme=day_theme(ordered, interest_order),
        activities=[PlannedActivity(c, s) for c, s in zip(ordered, slot_labels(len(ordered)))],
    )
    warnings = []
    if len(ordered) < per_day:
        warnings.append(
            f"Only {len(ordered)} new matching places were found nearby, so this day has fewer "
            f"than {per_day} activities."
        )
    return day, warnings


def day_pool(
    groups: list[list[Candidate]],
    anchor: tuple[float, float],
    exclude: set,
    avoid: set,
    size: int,
) -> list[Candidate]:
    """Candidates for regenerating one day: never places from other days
    (`exclude`); places not already on this day first, nearest the day's
    anchor; the day's current places (`avoid`) only after those."""
    unique, _ = clean_groups(groups)
    allowed = [c for c in unique if not (_candidate_keys(c) & exclude)]
    fresh = [c for c in allowed if not (_candidate_keys(c) & avoid)]
    stale = [c for c in allowed if _candidate_keys(c) & avoid]

    def key(c: Candidate):
        return (_dist(c, *anchor), c.place.id or "")

    return (sorted(fresh, key=key) + sorted(stale, key=key))[:size]


def exclude_keys(groups: list[list[Candidate]], used: set) -> list[list[Candidate]]:
    """Drop candidates already planned elsewhere (e.g. in an earlier city)."""
    if not used:
        return groups
    return [[c for c in g if not (_candidate_keys(c) & used)] for g in groups]


def plan_keys(plan: "Plan") -> set:
    keys: set = set()
    for day in plan.days:
        for item in day.activities:
            keys |= _candidate_keys(item.candidate)
    return keys
