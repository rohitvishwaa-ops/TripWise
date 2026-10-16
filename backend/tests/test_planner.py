"""Unit tests for the deterministic planner (pure functions, no network)."""

import itertools

import pytest

from places import CATEGORY_PATTERN, Place
from planner import (
    DEFAULT_CATEGORIES,
    INTEREST_CATEGORIES,
    Candidate,
    InsufficientPlacesError,
    activities_per_day,
    build_plan,
    day_capacities,
    day_theme,
    dedupe,
    distance_km,
    group_by_proximity,
    interest_queries,
    order_nearest_neighbour,
    select_balanced,
    slot_labels,
)
from trips import INTERESTS

CENTER = (35.0, 135.0)
_ids = itertools.count()


def cand(lat, lon, name=None, interest="culture", pid=None, categories=None):
    n = next(_ids)
    return Candidate(
        Place(
            id=pid if pid is not None else f"p{n}",
            name=name if name is not None else f"Place {n}",
            address=f"Address {n}",
            latitude=lat,
            longitude=lon,
            categories=categories or ["tourism.sights"],
        ),
        interest,
    )


# --- Interests and pace -----------------------------------------------------


def test_every_api_interest_has_valid_categories():
    assert set(INTERESTS) == set(INTEREST_CATEGORIES)
    for cats in [*INTEREST_CATEGORIES.values(), DEFAULT_CATEGORIES]:
        assert cats and all(CATEGORY_PATTERN.match(c) for c in cats)


@pytest.mark.parametrize(
    "interest, expected",
    [
        ("culture", "entertainment.museum"),
        ("history", "tourism.sights"),
        ("nature", "leisure.park"),
        ("food", "catering.restaurant"),
        ("entertainment", "entertainment.zoo"),
        ("beaches", "beach"),
    ],
)
def test_interest_mapping(interest, expected):
    [(name, categories)] = interest_queries([interest])
    assert name == interest and expected in categories.split(",")


def test_interest_queries_keep_order_and_dedupe():
    assert [i for i, _ in interest_queries(["food", "nature", "food"])] == ["food", "nature"]


def test_no_interests_falls_back_to_general_sightseeing():
    [(name, categories)] = interest_queries([])
    assert name == "sightseeing"
    assert categories.split(",") == DEFAULT_CATEGORIES


@pytest.mark.parametrize("pace, count", [("relaxed", 2), ("balanced", 3), ("packed", 5)])
def test_pace_activity_counts(pace, count):
    assert activities_per_day(pace) == count


# --- Cleaning and selection -------------------------------------------------


def test_dedupe_removes_unnamed_repeated_ids_and_same_named_spot():
    a = cand(35.0, 135.0, name="Kinkaku-ji", pid="a")
    items = [
        a,
        cand(35.0, 135.0, name="Kinkaku-ji", pid="a"),  # same id
        cand(35.00001, 135.00001, name="kinkaku-jí ", pid="b"),  # same name, same spot
        cand(35.1, 135.1, name="Kinkaku-ji", pid="c"),  # same name, elsewhere: kept
        cand(35.2, 135.2, name="", pid="d"),
        cand(35.3, 135.3, name="   ", pid="e"),
        Candidate(Place(id="f", name=None, latitude=1, longitude=1), "culture"),
    ]
    assert [c.place.id for c in dedupe(items)] == ["a", "c"]


def test_select_balanced_round_robins_interests():
    culture = [cand(35.0, 135.0 + i * 0.01, interest="culture") for i in range(5)]
    food = [cand(35.1, 135.0 + i * 0.01, interest="food") for i in range(2)]
    nature = [cand(35.2, 135.0 + i * 0.01, interest="nature") for i in range(5)]
    picked = select_balanced([culture, food, nature], 7)
    assert [c.interest for c in picked] == ["culture", "food", "nature", "culture", "food", "nature", "culture"]


def test_select_balanced_with_too_few_returns_everything():
    groups = [[cand(35, 135)], [], [cand(35, 135)]]
    assert len(select_balanced(groups, 10)) == 2


# --- Day allocation ---------------------------------------------------------


@pytest.mark.parametrize(
    "total, days, per_day, expected",
    [
        (9, 3, 3, [3, 3, 3]),
        (7, 3, 3, [3, 2, 2]),
        (20, 3, 3, [3, 3, 3]),  # never above the pace
        (3, 3, 5, [1, 1, 1]),
        (11, 3, 5, [4, 4, 3]),
    ],
)
def test_day_capacities(total, days, per_day, expected):
    assert day_capacities(total, days, per_day) == expected


def test_proximity_grouping_keeps_clusters_together():
    # Two tight clusters ~20 km apart, interleaved in the input.
    west = [cand(35.0, 135.0 + i * 0.001, interest="w") for i in range(3)]
    east = [cand(35.0, 135.22 + i * 0.001, interest="e") for i in range(3)]
    mixed = [x for pair in zip(west, east) for x in pair]
    groups = group_by_proximity(mixed, 2, [3, 3], CENTER)
    assert sorted({c.interest for c in g}.pop() for g in groups) == ["e", "w"]
    assert all(len({c.interest for c in g}) == 1 for g in groups)
    # Day 1 is the cluster nearest the city centre.
    assert groups[0][0].interest == "w"


def test_proximity_grouping_respects_capacities():
    items = [cand(35.0 + i * 0.01, 135.0) for i in range(7)]
    groups = group_by_proximity(items, 3, [3, 2, 2], CENTER)
    assert sorted(len(g) for g in groups) == [2, 2, 3]
    assert sorted(c.place.id for g in groups for c in g) == sorted(c.place.id for c in items)


def test_grouping_is_deterministic():
    items = [cand(35.0 + (i % 4) * 0.03, 135.0 + (i // 4) * 0.03) for i in range(12)]
    a = group_by_proximity(items, 4, [3, 3, 3, 3], CENTER)
    b = group_by_proximity(list(items), 4, [3, 3, 3, 3], CENTER)
    assert [[c.place.id for c in g] for g in a] == [[c.place.id for c in g] for g in b]


# --- Ordering and labels ----------------------------------------------------


def test_nearest_neighbour_orders_points_along_a_line():
    pts = {x: cand(35.0, 135.0 + x * 0.01, name=f"x{x}") for x in (4, 1, 3, 0, 2)}
    ordered = order_nearest_neighbour(list(pts.values()), (35.0, 134.99))
    assert [c.place.name for c in ordered] == ["x0", "x1", "x2", "x3", "x4"]


def test_nearest_neighbour_starts_closest_to_start():
    far, near = cand(35.5, 135.5, name="far"), cand(35.01, 135.01, name="near")
    assert order_nearest_neighbour([far, near], CENTER)[0].place.name == "near"


@pytest.mark.parametrize(
    "count, expected",
    [
        (0, []),
        (1, ["morning"]),
        (2, ["morning", "afternoon"]),
        (3, ["morning", "afternoon", "evening"]),
        (4, ["morning", "morning", "afternoon", "evening"]),
        (5, ["morning", "morning", "afternoon", "afternoon", "evening"]),
    ],
)
def test_slot_labels(count, expected):
    assert slot_labels(count) == expected


def test_day_theme():
    assert day_theme([cand(1, 1, interest="culture"), cand(1, 1, interest="food")]) == "Culture and Food"
    assert day_theme([cand(1, 1, interest="nature")]) == "Nature"
    assert day_theme([cand(1, 1, interest="sightseeing")]) == "Sightseeing"
    assert day_theme([]) is None
    mixed = [cand(1, 1, interest="food"), cand(1, 1, interest="culture")]
    assert day_theme(mixed, ["culture", "food"]) == "Culture and Food"


def test_distance_is_straight_line_km():
    assert distance_km(0, 0, 0, 1) == pytest.approx(111.2, abs=0.2)


# --- build_plan --------------------------------------------------------------


def grid(n, interest="culture", spacing=0.01):
    return [cand(35.0 + (i % 5) * spacing, 135.0 + (i // 5) * spacing, interest=interest) for i in range(n)]


@pytest.mark.parametrize("pace, per_day", [("relaxed", 2), ("balanced", 3), ("packed", 5)])
def test_build_plan_fills_days_by_pace(pace, per_day):
    plan = build_plan([grid(40)], CENTER, 3, pace)
    assert [len(d.activities) for d in plan.days] == [per_day] * 3
    assert plan.warnings == []
    for day in plan.days:
        assert [a.slot for a in day.activities] == slot_labels(per_day)


def test_build_plan_never_repeats_a_place_across_days():
    dup_heavy = grid(10) + grid(10)  # same coordinates twice, different ids
    culture = [cand(c.lat, c.lon, name=c.place.name, pid=c.place.id) for c in dup_heavy[:10]]
    plan = build_plan([culture, culture, grid(10, interest="food", spacing=0.02)], CENTER, 3, "packed")
    ids = [a.candidate.place.id for d in plan.days for a in d.activities]
    assert len(ids) == len(set(ids))


def test_build_plan_with_too_few_places_warns_and_spreads_evenly():
    plan = build_plan([grid(7)], CENTER, 3, "balanced")
    assert sorted(len(d.activities) for d in plan.days) == [2, 2, 3]
    assert plan.warnings and "Only 7" in plan.warnings[0]


def test_build_plan_fails_when_fewer_places_than_days():
    with pytest.raises(InsufficientPlacesError) as exc:
        build_plan([grid(2)], CENTER, 3, "relaxed")
    assert (exc.value.found, exc.value.needed) == (2, 3)


def test_build_plan_with_no_places():
    with pytest.raises(InsufficientPlacesError):
        build_plan([[], []], CENTER, 1, "relaxed")


def test_build_plan_ignores_unnamed_places():
    unnamed = [Candidate(Place(id=f"u{i}", name=None, latitude=35, longitude=135), "culture") for i in range(10)]
    with pytest.raises(InsufficientPlacesError):
        build_plan([unnamed], CENTER, 1, "relaxed")


def test_build_plan_is_deterministic():
    groups = [grid(15, "culture"), grid(15, "food", spacing=0.013)]
    a = build_plan(groups, CENTER, 4, "balanced")
    b = build_plan(groups, CENTER, 4, "balanced")
    flat = lambda p: [[(x.candidate.place.id, x.slot) for x in d.activities] for d in p.days]  # noqa: E731
    assert flat(a) == flat(b)


def test_select_balanced_spreads_out_clumped_places():
    # Three places on the same square, then two a few hundred metres away.
    clump = [cand(35.0, 135.0 + i * 0.0001, name=f"clump{i}") for i in range(3)]
    spread = [cand(35.0, 135.005 + i * 0.004, name=f"spread{i}") for i in range(2)]
    picked = select_balanced([clump + spread], 3)
    assert [c.place.name for c in picked] == ["clump0", "spread0", "spread1"]


def test_select_balanced_uses_clumped_places_when_nothing_else():
    clump = [cand(35.0, 135.0 + i * 0.0001, name=f"clump{i}") for i in range(3)]
    picked = select_balanced([clump], 3)
    assert [c.place.name for c in picked] == ["clump0", "clump1", "clump2"]


# --- build_day (single-day regeneration) ------------------------------------------

from planner import build_day, place_keys  # noqa: E402


def keys_of(*cands):
    out = set()
    for c in cands:
        out |= place_keys(c.place.id, c.place.name, c.lat, c.lon)
    return out


def test_build_day_never_uses_excluded_places():
    taken = [cand(35.0, 135.0 + i * 0.01, name=f"taken{i}") for i in range(3)]
    free = [cand(35.1, 135.0 + i * 0.01, name=f"free{i}") for i in range(3)]
    day, warnings = build_day([taken + free], (35.0, 135.0), "balanced", exclude=keys_of(*taken), avoid=set())
    assert sorted(a.candidate.place.name for a in day.activities) == ["free0", "free1", "free2"]
    assert warnings == []


def test_build_day_excludes_same_place_under_another_id():
    original = cand(35.0, 135.0, name="Museum X", pid="a")
    alias = cand(35.0001, 135.0001, name="museum x", pid="b")
    other = cand(35.2, 135.2, name="Other")
    day, _ = build_day([[alias, other]], (35.0, 135.0), "relaxed", exclude=keys_of(original), avoid=set())
    assert [a.candidate.place.name for a in day.activities] == ["Other"]


def test_build_day_prefers_fresh_places_then_falls_back():
    current = [cand(35.0, 135.0 + i * 0.01, name=f"cur{i}") for i in range(3)]
    fresh = [cand(35.05, 135.0, name="fresh0")]
    day, warnings = build_day([current + fresh], (35.0, 135.0), "balanced", exclude=set(), avoid=keys_of(*current))
    picked = [a.candidate.place.name for a in day.activities]
    assert "fresh0" in picked and len(picked) == 3
    assert warnings == []


def test_build_day_orders_near_anchor_and_labels_slots():
    far = cand(35.5, 135.5, name="far")
    near = [cand(35.0 + i * 0.01, 135.0, name=f"near{i}") for i in range(3)]
    day, _ = build_day([[far] + near], (35.0, 135.0), "balanced", exclude=set(), avoid=set())
    assert [a.candidate.place.name for a in day.activities] == ["near0", "near1", "near2"]
    assert [a.slot for a in day.activities] == ["morning", "afternoon", "evening"]


def test_build_day_with_nothing_left():
    taken = [cand(35.0, 135.0)]
    with pytest.raises(InsufficientPlacesError):
        build_day([taken], (35.0, 135.0), "relaxed", exclude=keys_of(*taken), avoid=set())
