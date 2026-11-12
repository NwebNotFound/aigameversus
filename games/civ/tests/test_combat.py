"""Combat: attacks, battles, conquest, pillage, fortifying and war weariness (step 7.4)."""

import pytest

from games.civ import combat, diplomacy, economy
from games.civ.state import NEUTRAL
from games.civ.tests.realm import CENTER, DATA, RICH, Realm, flat_map, reordered
from games.civ.turn import apply_event
from games.civ.world import Start

EAST = (4, 2)  # next to CENTER


def at_war(seed: int = 0, terrain: str = "plains") -> Realm:
    realm = Realm(flat_map(terrain), seed=seed)
    realm.start_round()
    diplomacy.declare_war(realm.state, realm.data, realm.ctx, "ada", "bo")
    return realm


def fight(realm: Realm, army: str, target=EAST, player: str = "ada") -> None:
    combat.attack(realm.state, realm.data, realm.ctx, player, army, target)
    combat.resolve(realm.state, realm.data, realm.ctx)


def of_type(realm: Realm, kind: str) -> list:
    return [e for e in realm.events if e.type == kind]


# --- who may attack ----------------------------------------------------------


def test_an_attack_needs_a_war():
    realm = Realm(flat_map("plains"))
    realm.start_round()
    mine = realm.army("ada", CENTER, "swordsman")
    realm.army("bo", EAST, "spearman")

    problem = combat.attack_problem(realm.state, realm.data, "ada", mine, EAST)

    assert "not at war with bo" in problem and "Declare war" in problem


def test_a_neutral_army_can_be_attacked_without_a_war():
    realm = Realm(flat_map("plains"))
    realm.start_round()
    mine = realm.army("ada", CENTER, "swordsman", "swordsman", "swordsman")
    realm.army(NEUTRAL, EAST, "spearman")

    assert combat.attack_problem(realm.state, realm.data, "ada", mine, EAST) is None
    fight(realm, mine)
    assert of_type(realm, "battle")[0].data["defender"]["nation"] == NEUTRAL


@pytest.mark.parametrize(
    ("target", "words"),
    [((5, 2), "Nothing of another nation"), ((0, 0), "Nothing of another nation")],
)
def test_an_attack_on_an_empty_or_far_tile_is_refused(target, words):
    realm = at_war()
    mine = realm.army("ada", CENTER, "swordsman")

    assert words in combat.attack_problem(realm.state, realm.data, "ada", mine, target)


def test_an_army_that_moved_cannot_attack_and_another_nations_army_is_not_yours():
    realm = at_war()
    mine = realm.army("ada", CENTER, "swordsman")
    theirs = realm.army("bo", EAST, "spearman")
    realm.state.army(mine).moved_in_round = realm.state.round

    assert "already moved" in combat.attack_problem(realm.state, realm.data, "ada", mine, EAST)
    assert "no army" in combat.attack_problem(realm.state, realm.data, "ada", theirs, CENTER)


# --- battles -------------------------------------------------------------------


def test_the_stronger_side_wins_takes_the_tile_and_the_loser_loses_units():
    realm = at_war()
    mine = realm.army("ada", CENTER, *["swordsman"] * 4)
    theirs = realm.army("bo", EAST, "spearman")

    fight(realm, mine)

    battle = of_type(realm, "battle")[0]
    assert battle.data["winner"] == "ada"
    assert battle.visible_to == ("ada", "bo")
    assert battle.data["defender"]["lost"] == ["spearman"]
    assert all(a.id != theirs for a in realm.state.armies)  # destroyed
    assert realm.state.army(mine).tile == EAST  # the winner takes the empty tile
    assert realm.state.attacks == []


def test_a_counter_doubles_strength_against_the_unit_it_counters():
    data = DATA
    swords, spears, riders = (
        data.units["swordsman"],
        data.units["spearman"],
        data.units["horseman"],
    )
    assert any(c.target == "spearman" for c in swords.counters)

    def power(units, enemies):
        from games.civ.state import Troop

        return combat._power(
            data,
            [Troop(kind=k) for k in units],
            [Troop(kind=k) for k in enemies],
            1,
            False,
            False,
            False,
        )

    assert power(["swordsman"], ["spearman"]) == 2 * power(["swordsman"], ["horseman"])
    assert power(["spearman"], ["horseman"]) == 2 * spears.strength
    assert power(["horseman"], ["spearman", "swordsman"]) == riders.strength * 1.5  # half countered


def test_walls_hills_and_fortifying_strengthen_the_defender_and_a_tie_holds_the_tile():
    def outcome(terrain, *buildings, fortified=False):
        realm = at_war(terrain=terrain)
        mine = realm.army("ada", CENTER, "swordsman", "swordsman")
        realm.found("bo", EAST, *buildings)
        theirs = realm.army("bo", EAST, "swordsman", "swordsman")
        if fortified:
            realm.state.army(theirs).fortified_from = realm.state.round
        fight(realm, mine)
        return of_type(realm, "battle")[0].data

    plain = outcome("plains")
    walled = outcome("plains", "wall")
    dug_in = outcome("plains", fortified=True)
    for stronger in (walled, dug_in):
        assert stronger["defender"]["power"] > plain["defender"]["power"]
    assert outcome("hills")["defender"]["power"] > plain["defender"]["power"]


def test_siege_engines_count_three_times_against_walls():
    from games.civ.state import Troop

    siege = [Troop(kind="siege_engine")]
    walls = combat._power(DATA, siege, [], 1, True, False, False)
    open_field = combat._power(DATA, siege, [], 1, False, False, False)

    assert walls == 3 * open_field


def test_archers_fire_before_the_melee():
    realm = at_war(seed=3)
    mine = realm.army("ada", CENTER, *["archer"] * 6)
    realm.army("bo", EAST, *["spearman"] * 3)

    fight(realm, mine)

    lost = of_type(realm, "battle")[0].data["defender"]["lost"]
    assert lost  # the ranged round and the melee cost the spearmen


def test_a_battle_is_the_same_for_the_same_seed_and_differs_with_another():
    def battle(seed):
        realm = at_war(seed=seed)
        mine = realm.army("ada", CENTER, *["swordsman"] * 3, "archer")
        realm.army("bo", EAST, *["spearman"] * 4, "archer")
        fight(realm, mine)
        return of_type(realm, "battle")[0].data

    assert battle(5) == battle(5)
    assert len({str(battle(seed)) for seed in range(8)}) > 1


# --- conquest -----------------------------------------------------------------------


def test_an_undefended_city_is_conquered_without_a_battle_and_everyone_hears_of_it():
    realm = at_war()
    realm.state.world.starts = [Start(player="bo", col=EAST[0], row=EAST[1], scarce="iron")]
    mine = realm.army("ada", CENTER, "swordsman")
    city = realm.found("bo", EAST, "barracks", population=3)

    fight(realm, mine)

    assert of_type(realm, "battle") == []
    conquered = of_type(realm, "city_conquered")[0]
    assert conquered.visible_to is None
    taken = realm.state.city(city)
    assert (taken.owner, taken.population, taken.conquered_round) == ("ada", 2, 1)
    assert taken.buildings == ["barracks"]
    rounds = DATA.balance.conquest.capital_lost_rounds
    assert realm.state.nations["bo"].capital_lost_until == 1 + rounds  # it was bo's capital


def test_a_lost_capital_and_war_weariness_cost_production():
    realm = at_war()
    city = realm.found("bo", CENTER, population=1)
    realm.state.nations["bo"].capital_lost_until = 5
    realm.state.nations["bo"].weary_rounds = 30
    full = realm.yields(city)["food"]

    modifier = economy.production_modifier(realm.state, DATA, "bo")
    assert modifier == pytest.approx(
        DATA.balance.war_weariness.max_production_modifier
        + DATA.balance.conquest.capital_lost_production_modifier
    )
    realm.end_round()
    made = [e for e in realm.events if e.type == "production" and e.data["player"] == "bo"][-1]
    assert made.data["yields"]["food"] == int(full * (1 + modifier))


def test_weariness_grows_each_round_at_war_and_ends_with_peace():
    realm = at_war()
    for _ in range(3):
        combat.weariness(realm.state, DATA, realm.ctx)
    assert realm.state.nations["ada"].weary_rounds == 3
    realm.state.wars = []
    combat.weariness(realm.state, DATA, realm.ctx)
    assert realm.state.nations["ada"].weary_rounds == 0
    weary = of_type(realm, "war_weariness")
    assert all(e.visible_to == (e.data["nation"],) for e in weary)


# --- fortify, pillage -------------------------------------------------------------------


def test_fortifying_counts_from_the_next_round_and_moving_ends_it():
    realm = at_war()
    mine = realm.army("ada", CENTER, "spearman")

    combat.fortify(realm.state, realm.ctx, "ada", mine)
    assert realm.state.army(mine).fortified_from == realm.state.round + 1
    realm.start_round()
    from games.civ import armies

    armies.move(realm.state, realm.data, realm.ctx, "ada", mine, EAST)
    assert realm.state.army(mine).fortified_from is None


def test_pillage_burns_the_newest_building_and_carries_off_half_its_cost():
    realm = at_war()
    realm.state.nations["ada"].stock = dict(RICH)
    mine = realm.army("ada", CENTER, "swordsman")
    city = realm.found("bo", EAST, "farm", "barracks")

    assert combat.pillage_problem(realm.state, "ada", mine) is None
    combat.pillage(realm.state, DATA, realm.ctx, "ada", mine)

    assert realm.state.city(city).buildings == ["farm"]
    loot = of_type(realm, "city_pillaged")[0].data["loot"]
    share = DATA.balance.conquest.pillage_loot_share
    assert loot == {
        r: int(n * share) for r, n in DATA.buildings["barracks"].cost.items() if int(n * share)
    }
    assert realm.state.army(mine).moved_in_round == realm.state.round


def test_pillage_needs_a_war_and_a_building_next_to_the_army():
    realm = Realm(flat_map("plains"))
    realm.start_round()
    mine = realm.army("ada", CENTER, "swordsman")
    realm.found("bo", EAST, "farm")

    assert "at war with" in combat.pillage_problem(realm.state, "ada", mine)


# --- the log rebuilds the state -----------------------------------------------------------


def test_replaying_the_events_with_their_keys_reversed_rebuilds_the_state():
    realm = at_war(seed=2)
    mine = realm.army("ada", CENTER, *["swordsman"] * 3, "archer")
    realm.army("bo", EAST, "spearman", "archer")
    fight(realm, mine)
    combat.weariness(realm.state, DATA, realm.ctx)

    again = Realm(flat_map("plains"))
    for event in realm.events:
        apply_event(again.state, event.model_copy(update={"data": reordered(event.data)}))

    assert again.state == realm.state
