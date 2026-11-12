"""Victory: domination, the economic countdown, the round limit's score, and the placements."""

import pytest

from games.civ import victory
from games.civ.tests.realm import DATA, Realm, flat_map

PLAYERS = ("ada", "bo", "cy", "di")


def realm(players=PLAYERS):
    world = Realm(flat_map("plains"), players)
    world.start_round()
    return world


def cities(world, owner, count):
    for _ in range(count):
        col = len(world.state.cities) % 7
        row = len(world.state.cities) // 7
        world.found(owner, (col, row))


def last(world):
    return world.events[-1]


def test_the_score_counts_cities_population_gold_and_reputation():
    world = realm()
    cities(world, "ada", 2)
    world.state.city("c1").population = 3
    world.state.nations["ada"].stock["gold"] = 57
    world.state.nations["ada"].reputation = 49

    # 2 cities x 10 + 4 population + 57 // 10 + 49 // 5
    assert victory.score(world.state, DATA, "ada") == 20 + 4 + 5 + 9


def test_domination_needs_half_the_cities_and_more_than_anyone_else():
    world = realm()
    cities(world, "ada", 2)
    cities(world, "bo", 2)
    assert victory.dominating(world.state, DATA) is None  # half, but not more than bo

    cities(world, "ada", 1)
    assert victory.dominating(world.state, DATA) == "ada"  # 3 of 5

    assert victory.check(world.state, DATA, world.ctx) == "domination"
    won = last(world)
    assert (won.type, won.visible_to, won.data["winners"]) == ("victory", None, ["ada"])
    assert world.state.victory["kind"] == "domination"
    assert won.data["placements"][0] == {"player": "ada", "rank": 1}


@pytest.mark.parametrize(
    ("held", "winner"),
    [
        ({"ada": 2, "bo": 1, "cy": 1}, "ada"),  # exactly half, more than anyone else
        ({"ada": 1, "bo": 1, "cy": 1, "di": 1}, None),  # a quarter
        ({"ada": 2, "bo": 2}, None),  # half, but tied
    ],
)
def test_domination_at_exactly_the_share(held, winner):
    world = realm()
    for owner, count in held.items():
        cities(world, owner, count)

    assert DATA.victory.domination.city_share == 0.5
    assert victory.dominating(world.state, DATA) == winner


def test_the_economic_countdown_is_public_and_resets_when_the_gold_drops():
    world = realm()
    cities(world, "ada", 1)
    for player in PLAYERS[1:]:
        cities(world, player, 1)
    world.state.nations["ada"].stock["gold"] = DATA.victory.economy.gold

    victory.check(world.state, DATA, world.ctx)
    assert (last(world).type, last(world).visible_to) == ("economy_countdown", None)
    assert world.state.rich_rounds["ada"] == 1

    world.state.nations["ada"].stock["gold"] = 10
    victory.check(world.state, DATA, world.ctx)
    assert world.state.rich_rounds["ada"] == 0


def test_holding_the_gold_long_enough_wins():
    world = realm()
    for player in PLAYERS:
        cities(world, player, 1)
    world.state.nations["bo"].stock["gold"] = DATA.victory.economy.gold + 1

    kinds = [
        victory.check(world.state, DATA, world.ctx) for _ in range(DATA.victory.economy.hold_rounds)
    ]

    assert kinds[:-1] == [None] * (DATA.victory.economy.hold_rounds - 1)
    assert kinds[-1] == "economy" and world.state.victory["winners"] == ["bo"]


def test_at_the_round_limit_the_best_score_wins_and_equal_scores_share():
    world = realm()
    for player in PLAYERS:
        cities(world, player, 1)
    world.state.city("c2").population = 3  # bo
    world.state.round = DATA.victory.round_limit.rounds

    assert victory.check(world.state, DATA, world.ctx) == "round_limit"
    placements = {p["player"]: p["rank"] for p in last(world).data["placements"]}
    assert placements == {"bo": 1, "ada": 2, "cy": 2, "di": 2}


def test_before_the_limit_and_without_a_condition_nobody_wins():
    world = realm()
    for player in PLAYERS:
        cities(world, player, 1)

    assert victory.check(world.state, DATA, world.ctx) is None
    assert world.state.victory is None
    assert not any(e.type == "victory" for e in world.events)


def test_a_won_match_stays_won():
    world = realm()
    cities(world, "ada", 3)
    victory.check(world.state, DATA, world.ctx)
    count = len(world.events)

    assert victory.check(world.state, DATA, world.ctx) == "domination"
    assert len(world.events) == count


@pytest.mark.parametrize("winner_score_rank", [1])
def test_placements_rank_the_others_by_score_after_the_winner(winner_score_rank):
    world = realm()
    cities(world, "ada", 3)  # ada dominates
    cities(world, "bo", 1)
    world.state.nations["bo"].stock["gold"] = 400  # bo has the best score
    world.state.nations["cy"].stock["gold"] = 100

    victory.check(world.state, DATA, world.ctx)

    placements = {p["player"]: p["rank"] for p in last(world).data["placements"]}
    assert placements["ada"] == winner_score_rank
    assert placements["bo"] == 2 and placements["cy"] == 3 and placements["di"] == 4
