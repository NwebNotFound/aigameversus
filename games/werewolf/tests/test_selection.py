import random
from collections import Counter

import pytest

from arena.engine.rng import derive_rng
from games.werewolf.selection import (
    EVEN_MARGIN,
    MAX_PLAYERS,
    MIN_PLAYERS,
    apply_template,
    assign_roles,
    balance,
    fill_selection,
    load_roles,
    load_templates,
    validate_selection,
)

PLAYER_COUNTS = range(MIN_PLAYERS, MAX_PLAYERS + 1)


def codes(selection: dict[str, int], players: int) -> list[str]:
    return [problem.code for problem in validate_selection(selection, players)]


# --- loading -----------------------------------------------------------------


def test_roles_load_with_weights_from_the_files():
    roles = load_roles()

    assert len(roles) == 16
    assert roles["seer"].weight == 7
    assert roles["witch"].weight == 4
    assert roles["werewolf"].weight == -6
    assert roles["werewolf"].unique is False
    assert roles["seer"].unique is True


def test_wolves_and_the_white_werewolf_count_as_wolves():
    wolf_side = {role_id for role_id, role in load_roles().items() if role.hunts_with_wolves}

    assert wolf_side == {"werewolf", "prime_wolf", "white_wolf"}


# --- filling -----------------------------------------------------------------


def test_free_seats_are_filled_with_villagers():
    assert fill_selection({"werewolf": 2, "seer": 1}, 8) == {
        "werewolf": 2,
        "seer": 1,
        "villager": 5,
    }


def test_fill_adds_to_chosen_villagers_and_drops_zero_counts():
    filled = fill_selection({"werewolf": 1, "villager": 2, "witch": 0}, 6)

    assert filled == {"werewolf": 1, "villager": 5}


def test_full_selection_is_left_alone():
    assert fill_selection({"werewolf": 2, "villager": 4}, 6) == {"werewolf": 2, "villager": 4}


# --- validation, one rule each ----------------------------------------------


def test_a_classic_mix_is_valid():
    assert validate_selection({"werewolf": 2, "seer": 1, "witch": 1, "hunter": 1}, 8) == []


def test_needs_a_wolf():
    problems = validate_selection({"seer": 1}, 8)

    assert [p.code for p in problems] == ["no_wolf"]
    assert problems[0].message == "add at least one wolf"


def test_white_werewolf_alone_counts_as_a_wolf():
    assert validate_selection({"white_wolf": 1}, 8) == []


@pytest.mark.parametrize(
    ("wolves", "players", "ok"),
    [(3, 8, True), (4, 8, False), (2, 6, True), (3, 6, False), (3, 7, True), (4, 7, False)],
)
def test_wolves_must_be_fewer_than_half(wolves: int, players: int, ok: bool):
    assert ("too_many_wolves" not in codes({"werewolf": wolves}, players)) is ok


def test_too_many_wolves_counts_special_wolves_and_explains_the_limit():
    problems = validate_selection({"werewolf": 2, "prime_wolf": 1, "white_wolf": 1}, 8)

    assert [p.code for p in problems] == ["too_many_wolves"]
    assert "4 wolves for 8 players" in problems[0].message
    assert "at most 3" in problems[0].message


def test_unique_role_at_most_once_names_the_role():
    problems = validate_selection({"werewolf": 1, "seer": 2}, 8)

    assert [p.code for p in problems] == ["unique_role_repeated"]
    assert problems[0].role == "seer"
    assert problems[0].message == "Seherin may appear only once, selected 2 times"


def test_every_repeated_unique_role_is_reported():
    problems = validate_selection({"werewolf": 1, "seer": 2, "witch": 3}, 10)

    assert [(p.code, p.role) for p in problems] == [
        ("unique_role_repeated", "seer"),
        ("unique_role_repeated", "witch"),
    ]


def test_villagers_and_werewolves_may_repeat():
    assert validate_selection({"werewolf": 2, "villager": 6}, 8) == []


def test_not_more_roles_than_players():
    problems = validate_selection({"werewolf": 2, "villager": 5}, 6)

    assert [p.code for p in problems] == ["too_many_roles"]
    assert problems[0].message == "7 roles chosen for 6 players; remove 1"


@pytest.mark.parametrize(("players", "code"), [(5, "too_few_players"), (17, "too_many_players")])
def test_player_count_must_be_6_to_16(players: int, code: str):
    problems = validate_selection({"werewolf": 1}, players)

    assert code in [p.code for p in problems]
    assert str(players) in next(p.message for p in problems if p.code == code)


@pytest.mark.parametrize("players", [MIN_PLAYERS, MAX_PLAYERS])
def test_6_and_16_players_are_allowed(players: int):
    assert validate_selection({"werewolf": 2}, players) == []


def test_unknown_role_is_named():
    problems = validate_selection({"werewolf": 1, "vampire": 1}, 8)

    assert [(p.code, p.role) for p in problems] == [("unknown_role", "vampire")]
    assert "'vampire' is not a role" in problems[0].message


@pytest.mark.parametrize("count", [-1, 1.5, True])
def test_bad_counts_are_rejected(count):
    problems = validate_selection({"werewolf": 1, "seer": count}, 8)

    assert [(p.code, p.role) for p in problems] == [("invalid_count", "seer")]
    assert problems[0].message.startswith("Seherin: count must be a whole number")


def test_several_problems_are_reported_together():
    assert codes({"seer": 2, "villager": 10}, 5) == [
        "too_few_players",
        "unique_role_repeated",
        "too_many_roles",
        "no_wolf",
    ]


# --- balance -----------------------------------------------------------------


def test_balance_sums_weights_times_counts():
    result = balance({"werewolf": 2, "seer": 1, "witch": 1, "villager": 4})

    assert result.total == -12 + 7 + 4 + 4


@pytest.mark.parametrize(
    ("total_villagers", "expected"),
    [(0, "even"), (4, "even"), (5, "village")],
)
def test_village_threshold(total_villagers: int, expected: str):
    # 1 werewolf (-6) + 1 seer (+7) = +1, each villager +1.
    selection = {"werewolf": 1, "seer": 1, "villager": total_villagers}

    result = balance(selection)

    assert result.total == 1 + total_villagers
    assert result.verdict == expected


@pytest.mark.parametrize(
    ("total", "expected"), [(-EVEN_MARGIN, "even"), (-EVEN_MARGIN - 1, "wolves")]
)
def test_wolf_threshold(total: int, expected: str):
    # werewolves at -6 each, villagers at +1: pick villagers so the total hits `total`.
    selection = {"werewolf": 2, "villager": total + 12}

    result = balance(selection)

    assert result.total == total
    assert result.verdict == expected


def test_margin_is_less_than_one_werewolf():
    assert -load_roles()["werewolf"].weight > EVEN_MARGIN


# --- templates ---------------------------------------------------------------


FIXED_TEMPLATES = ["classic", "duesterwald", "chaos"]


@pytest.mark.parametrize("template_id", FIXED_TEMPLATES)
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_fixed_templates_fill_to_a_valid_selection(template_id: str, players: int):
    template = load_templates()[template_id]
    if players < template.min_players:
        with pytest.raises(ValueError, match=f"needs {template.min_players}-16 players"):
            apply_template(template_id, players)
        return

    selection = apply_template(template_id, players)

    assert sum(selection.values()) == players
    assert validate_selection(selection, players) == []


def test_classic_template_has_the_spec_roles():
    assert apply_template("classic", 8) == {
        "werewolf": 2, "seer": 1, "witch": 1, "hunter": 1, "villager": 3,
    }  # fmt: skip


def test_classic_wolves_scale_with_the_table():
    wolves = {n: apply_template("classic", n)["werewolf"] for n in PLAYER_COUNTS}

    assert wolves == {6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 3, 13: 3, 14: 3, 15: 3, 16: 4}
    assert set(load_templates()["classic"].by_players["werewolf"]) == set(PLAYER_COUNTS)


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_classic_is_even_at_every_table_size(players: int):
    assert balance(apply_template("classic", players)).verdict == "even"


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_random_balanced_is_valid_and_near_zero(players: int):
    for seed in range(5):
        selection = apply_template("random_balanced", players, derive_rng(seed, "roles"))

        assert sum(selection.values()) == players
        assert validate_selection(selection, players) == []
        assert balance(selection).verdict == "even"


def test_random_balanced_is_the_same_for_the_same_seed():
    first = apply_template("random_balanced", 10, derive_rng(42, "roles"))
    second = apply_template("random_balanced", 10, derive_rng(42, "roles"))

    assert first == second


def test_random_balanced_varies_with_the_seed():
    mixes = {
        tuple(sorted(apply_template("random_balanced", 12, derive_rng(seed, "roles")).items()))
        for seed in range(10)
    }

    assert len(mixes) > 1


def test_random_template_needs_an_rng():
    with pytest.raises(ValueError, match="needs an rng"):
        apply_template("random_balanced", 8)


def test_unknown_template_is_rejected():
    with pytest.raises(ValueError, match="unknown template 'grimdark'"):
        apply_template("grimdark", 8)


# --- assignment --------------------------------------------------------------


PLAYERS = [f"p{i}" for i in range(8)]


def test_every_player_gets_one_role_of_the_filled_selection():
    roles = assign_roles({"werewolf": 2, "seer": 1}, PLAYERS, random.Random(1))

    assert set(roles) == set(PLAYERS)
    assert Counter(roles.values()) == {"werewolf": 2, "seer": 1, "villager": 5}


def test_same_seed_deals_the_same_roles():
    first = assign_roles({"werewolf": 2, "seer": 1}, PLAYERS, derive_rng(9, "roles"))
    second = assign_roles({"werewolf": 2, "seer": 1}, PLAYERS, derive_rng(9, "roles"))

    assert first == second


def test_the_deal_does_not_depend_on_selection_order():
    first = assign_roles({"werewolf": 2, "seer": 1}, PLAYERS, derive_rng(9, "roles"))
    second = assign_roles({"seer": 1, "werewolf": 2}, PLAYERS, derive_rng(9, "roles"))

    assert first == second


def test_different_seeds_deal_differently():
    deals = {
        tuple(assign_roles({"werewolf": 2, "seer": 1}, PLAYERS, derive_rng(s, "roles")).values())
        for s in range(10)
    }

    assert len(deals) > 1


def test_invalid_selection_is_not_dealt():
    with pytest.raises(ValueError, match="Seherin may appear only once"):
        assign_roles({"werewolf": 1, "seer": 2}, PLAYERS, random.Random(1))


def test_players_must_be_distinct():
    with pytest.raises(ValueError, match="distinct"):
        assign_roles({"werewolf": 1}, ["a", "a", "b", "c", "d", "e"], random.Random(1))
