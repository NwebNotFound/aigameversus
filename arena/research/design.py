"""Balanced seatings for four-seat tables.

A seating is a tuple of four entries, seat `p1` first. In the games so far the
seat carries the luck of a seed (cards, revolver), and the seat order is the
turn order. Playing one seed with every seating of a design therefore gives
each entry the same luck once per seat.
"""

from collections.abc import Sequence
from itertools import combinations

SEATS = 4

# A Williams design for four entries: every entry sits in every seat once, and
# every entry sits directly after every other entry exactly once (p4 to p1,
# the step around the table, not counted).
_WILLIAMS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))


def blocks_of_four(entries: Sequence[str]) -> list[tuple[str, ...]]:
    """The 14 tables of four that balance eight entries.

    Every entry sits at 7 tables and every pair of entries meets at exactly 3.
    The tables come in pairs that together hold all eight entries. They are the
    planes of the cube whose corners are the numbers 0 to 7 in binary: for each
    of the 7 ways to split the corners by the parity of chosen bits, one table
    per half.
    """
    if len(entries) != 8 or len(set(entries)) != 8:
        raise ValueError("this design needs exactly 8 different entries")
    blocks = []
    for bits in range(1, 8):
        halves: tuple[list[str], list[str]] = ([], [])
        for corner, entry in enumerate(entries):
            halves[(corner & bits).bit_count() % 2].append(entry)
        blocks += [tuple(halves[0]), tuple(halves[1])]
    return blocks


def rotations(table: Sequence[str]) -> list[tuple[str, ...]]:
    """Four seatings of four entries: each entry in each seat once (Williams design)."""
    _need_four(table)
    return [tuple(table[i] for i in order) for order in _WILLIAMS]


def guest_seatings(guest: str, hosts: Sequence[str]) -> list[tuple[str, ...]]:
    """Twelve seatings of one guest among three hosts.

    The guest sits in every seat three times; the hosts keep their order around
    the table and start it at each of them once, so every host sits directly
    before and directly after the guest equally often.
    """
    if len(hosts) != SEATS - 1 or len({guest, *hosts}) != SEATS:
        raise ValueError("this design needs one guest and 3 different hosts")
    seatings = []
    for seat in range(SEATS):
        for shift in range(len(hosts)):
            order = [*hosts[shift:], *hosts[:shift]]
            order.insert(seat, guest)
            seatings.append(tuple(order))
    return seatings


def mirror_seatings(first: str, second: str) -> list[tuple[str, ...]]:
    """The six seatings of two entries that take two seats each."""
    if first == second:
        raise ValueError("a mirror table needs two different entries")
    return [
        tuple(first if seat in pair else second for seat in range(SEATS))
        for pair in combinations(range(SEATS), 2)
    ]


def _need_four(table: Sequence[str]) -> None:
    if len(table) != SEATS or len(set(table)) != SEATS:
        raise ValueError("a table needs exactly 4 different entries")
