"""The trust rules of config/memory/trust.yaml and how one match changes trust."""

import pytest
import yaml

from arena.memory.facts import KINDS, Fact
from arena.memory.trust import TRUST_PATH, load_rules, match_changes


def test_the_shipped_rules_cover_every_fact():
    rules = load_rules()

    assert (rules.limits.min, rules.limits.max) == (-100, 100)
    for game, kinds in KINDS.items():
        assert set(rules.facts[game]) == kinds


def write(tmp_path, change):
    data = yaml.safe_load(TRUST_PATH.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "trust.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_a_fact_without_a_rule_is_refused(tmp_path):
    path = write(tmp_path, lambda d: d["facts"]["poker"].pop("bluff_called"))

    with pytest.raises(ValueError, match=r"(?s)trust.yaml: .*poker: no rule for bluff_called"):
        load_rules(path)


def test_a_rule_for_no_fact_is_refused(tmp_path):
    path = write(tmp_path, lambda d: d["facts"]["poker"].update(folded={"trust": 1, "note": "x"}))

    with pytest.raises(ValueError, match="poker: no fact is called folded"):
        load_rules(path)


def test_an_unknown_field_is_refused(tmp_path):
    path = write(tmp_path, lambda d: d["limits"].update(decay=2))

    with pytest.raises(ValueError, match="decay"):
        load_rules(path)


def test_a_match_adds_up_its_facts_per_pair_with_a_note_each():
    rules = load_rules()
    facts = [
        Fact(observer="a", about="b", kind="voted_against_me", round=1),
        Fact(observer="a", about="b", kind="voted_against_me", round=2),
        Fact(observer="b", about="a", kind="packmate"),
    ]

    changes = match_changes("werewolf", facts, rules)

    vote = rules.facts["werewolf"]["voted_against_me"].trust
    assert changes[("a", "b")].trust == 2 * vote
    assert changes[("a", "b")].notes == ["voted against me on day 1", "voted against me on day 2"]
    assert changes[("b", "a")].trust == rules.facts["werewolf"]["packmate"].trust
    assert set(changes) == {("a", "b"), ("b", "a")}


@pytest.mark.parametrize(("trust", "clamped"), [(-250, -100), (-100, -100), (7, 7), (101, 100)])
def test_trust_stays_in_its_range(trust, clamped):
    assert load_rules().clamp(trust) == clamped
