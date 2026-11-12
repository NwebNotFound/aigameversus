"""The styles and languages of the chronicle, and the words for Werewolf causes of death.

The chronicle's own words live in `templates/<game>.<lang>.yaml`; `CAUSES` is shared with the
transcript and the analytics, which say how a Werewolf player died the same way.
"""

STYLES = ("epic", "news", "sports", "novel")
LANGS = ("en", "de")

# fmt: off
CAUSES = {
    "en": {
        "wolves": "torn apart by the wolves", "executed": "executed by the village",
        "poison": "poisoned", "hunter": "shot by the Hunter", "grief": "dead of grief",
        "caught_spying": "caught spying", "white_wolf": "killed by the White Werewolf",
        "scapegoat": "taken as the scapegoat",
    },
    "de": {
        "wolves": "von den Wölfen gerissen", "executed": "vom Dorf hingerichtet",
        "poison": "vergiftet", "hunter": "vom Jäger erschossen", "grief": "vor Kummer gestorben",
        "caught_spying": "beim Spionieren erwischt", "white_wolf": "vom Weißen Werwolf getötet",
        "scapegoat": "als Sündenbock geopfert",
    },
}
# fmt: on
