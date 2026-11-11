"""Seeded randomness. Every random number in a match derives from the match seed."""

import hashlib
import json
import random


def derive_rng(seed: int, *key: str | int) -> random.Random:
    """Return the random stream named by `key` for this seed.

    The same seed and key always give the same stream, and streams with
    different keys are independent. Because a stream depends on nothing else,
    a match can be continued from its event log without saved generator state.
    """
    material = json.dumps([seed, *key]).encode()
    return random.Random(int.from_bytes(hashlib.sha256(material).digest()))
