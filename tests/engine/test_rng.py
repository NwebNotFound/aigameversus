from arena.engine.rng import derive_rng


def draws(*key):
    rng = derive_rng(*key)
    return tuple(rng.random() for _ in range(5))


def test_same_seed_and_key_give_the_same_stream():
    assert draws(42, "deal", 1) == draws(42, "deal", 1)


def test_seed_and_every_key_part_change_the_stream():
    streams = {draws(42, "deal", 1), draws(43, "deal", 1), draws(42, "deal", 2), draws(42, "x", 1)}

    assert len(streams) == 4
