"""Seatings: every balance a schedule relies on, counted."""

from collections import Counter
from itertools import combinations

import pytest

from arena.research.design import (
    all_tables,
    blocks_of_four,
    guest_seatings,
    mirror_seatings,
    rotations,
)

EIGHT = list("abcdefgh")


def test_fourteen_tables_seat_every_entry_7_times_and_every_pair_3_times():
    blocks = blocks_of_four(EIGHT)

    assert len(blocks) == 14
    assert all(len(set(block)) == 4 for block in blocks)
    assert Counter(entry for block in blocks for entry in block) == dict.fromkeys(EIGHT, 7)
    pairs = Counter(pair for block in blocks for pair in combinations(sorted(block), 2))
    assert len(pairs) == 28
    assert set(pairs.values()) == {3}


def test_tables_come_in_pairs_that_hold_all_eight():
    blocks = blocks_of_four(EIGHT)

    for first, second in zip(blocks[::2], blocks[1::2], strict=True):
        assert sorted(first + second) == EIGHT


def test_blocks_need_eight_different_entries():
    with pytest.raises(ValueError, match="exactly 8"):
        blocks_of_four(list("abcdefg"))
    with pytest.raises(ValueError, match="exactly 8"):
        blocks_of_four(list("abcdefga"))


def test_rotations_put_every_entry_in_every_seat_once():
    seatings = rotations("abcd")

    assert len(seatings) == 4
    for seat in range(4):
        assert sorted(seating[seat] for seating in seatings) == list("abcd")


def test_rotations_let_every_entry_follow_every_other_once():
    follows = Counter(
        (seating[seat], seating[seat + 1]) for seating in rotations("abcd") for seat in range(3)
    )

    assert len(follows) == 12
    assert set(follows.values()) == {1}


def test_rotations_need_four_different_entries():
    with pytest.raises(ValueError, match="exactly 4"):
        rotations("abc")
    with pytest.raises(ValueError, match="exactly 4"):
        rotations("abca")


def test_guest_sits_in_every_seat_three_times_and_next_to_every_host_equally():
    seatings = guest_seatings("g", ["x", "y", "z"])

    assert len(set(seatings)) == 12
    assert Counter(seating.index("g") for seating in seatings) == {0: 3, 1: 3, 2: 3, 3: 3}
    before = Counter(seating[(seating.index("g") - 1) % 4] for seating in seatings)
    after = Counter(seating[(seating.index("g") + 1) % 4] for seating in seatings)
    assert before == after == {"x": 4, "y": 4, "z": 4}


def test_hosts_keep_their_order_around_the_table():
    for seating in guest_seatings("g", ["x", "y", "z"]):
        hosts = [entry for entry in seating if entry != "g"]
        assert hosts in (["x", "y", "z"], ["y", "z", "x"], ["z", "x", "y"])


def test_guest_seatings_need_one_guest_and_three_hosts():
    with pytest.raises(ValueError, match="3 different hosts"):
        guest_seatings("g", ["x", "y"])
    with pytest.raises(ValueError, match="3 different hosts"):
        guest_seatings("x", ["x", "y", "z"])


def test_mirror_seatings_are_the_six_ways_to_give_two_seats_each():
    seatings = mirror_seatings("high", "low")

    assert len(set(seatings)) == 6
    assert all(Counter(seating) == {"high": 2, "low": 2} for seating in seatings)
    for seat in range(4):
        assert Counter(seating[seat] for seating in seatings) == {"high": 3, "low": 3}


def test_mirror_seatings_need_two_different_entries():
    with pytest.raises(ValueError, match="two different"):
        mirror_seatings("same", "same")


def test_all_tables_of_six_seat_every_entry_10_times_and_every_pair_6_times():
    tables = all_tables(list("abcdef"))

    assert len(tables) == 15
    assert Counter(entry for table in tables for entry in table) == dict.fromkeys("abcdef", 10)
    pairs = Counter(pair for table in tables for pair in combinations(table, 2))
    assert len(pairs) == 15 and set(pairs.values()) == {6}


def test_all_tables_need_six_different_entries():
    with pytest.raises(ValueError, match="exactly 6"):
        all_tables(list("abcde"))
