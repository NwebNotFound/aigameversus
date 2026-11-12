"""Werewolf: a hidden-role game of night kills, day debates and public votes.

The match runs as a queue of steps, each one player's turn: night actions in
the order of the role files, wolf votes, the day's speeches and votes, and
death effects such as the Hunter's shot. Events rebuild the queue, so a
replay needs no extra state.

Hidden information, and who may see it:
- a player's role: only that player (`role_assigned`) until they die;
- the pack: only its members (`pack_revealed`, wolf votes and wolf chat);
- a night action and its answer: only the acting player (`seer_inspected`, ...).
"""

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.types import MESSAGE, Action, Event, Placement, PlayerId, ToolSpec, TurnMode
from games.werewolf import prompt
from games.werewolf.abilities import NIGHT, implemented, target_schema, tool
from games.werewolf.narrator import LANGUAGES, narrate
from games.werewolf.selection import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    ROOT,
    apply_template,
    assign_roles,
    fill_selection,
    load_roles,
    validate_selection,
)

MAX_SPEECH_WORDS = 120
MAX_SHORT_WORDS = 40  # wolf chat and vote reasons
MAX_WOLF_MESSAGES = 2
DISCUSSION_ROUNDS = 2
MAX_NIGHTS = 30  # a match still undecided after the 30th day ends without a winner


def cycle_turns(players: int) -> int:
    """The most turns one night and day can take with this many players (D-046).

    Night: one role step and one wolf step per player, one extra for the Prime
    Wolf's choice, two wolf chats per player. Day: one captain vote, two
    speeches and one vote per player, and up to two death effects per player
    (Hunter's shot, captain's handover). Each of these may come with one
    lover_chat turn.
    """
    night = players + players + 1 + 2 * players
    day = players + DISCUSSION_ROUNDS * players + players + 2 * players
    return 2 * (night + day)


WOLF_NIGHT_ORDER = 6
RAVEN_VOTES = 2
OPTIONS = yaml.safe_load((ROOT / "options.yaml").read_text(encoding="utf-8"))

Phase = Literal["setup", "night", "morning", "day", "dusk", "over"]


class Step(BaseModel):
    kind: Literal["night", "wolf", "captain_vote", "speak", "vote", "hunter", "pass_captaincy"]
    player: PlayerId
    ability: str | None = None  # night steps: the handler from the role file


class WerewolfState(BaseModel):
    players: list[PlayerId]  # seating order
    selection: dict[str, int] = {}  # filled role counts; empty until setup for random templates
    template: str | None = None
    roles_public: bool = False
    roles: dict[PlayerId, str] = {}
    pack: list[PlayerId] = []  # players who hunt with the wolves
    alive: list[PlayerId] = []
    revealed: dict[PlayerId, str] = {}  # roles shown on death
    night: int = 0
    day: int = 0
    phase: Phase = "setup"
    queue: list[Step] = []
    wolf_messages: dict[PlayerId, int] = {}
    wolf_votes: dict[PlayerId, PlayerId] = {}  # in the order they were cast
    potions: dict[str, bool] = {"heal": True, "poison": True}
    healed: PlayerId | None = None
    poisoned: PlayerId | None = None
    seer_results: dict[PlayerId, dict[PlayerId, str]] = {}
    speaking_order: list[PlayerId] = []
    day_votes: dict[PlayerId, PlayerId | None] = {}
    winner: str | None = None
    winners: list[PlayerId] = []
    language: str = "de"
    captain_enabled: bool = True
    captain_weight: int = 2
    successor_on_death: bool = True
    captain: PlayerId | None = None
    captain_votes: dict[PlayerId, PlayerId] = {}
    lovers: list[PlayerId] = []
    lover_talked: bool = False  # a lover used lover_chat in the current step
    protected: PlayerId | None = None
    last_protected: PlayerId | None = None
    caught_girl: PlayerId | None = None  # the Little Girl caught spying tonight
    elder_hit: list[PlayerId] = []  # Elders who already survived a wolf attack
    powers_lost: bool = False  # the village executed its Elder
    no_vote: list[PlayerId] = []  # revealed Village Idiots
    marked: PlayerId | None = None  # the Raven's mark for the coming day
    mark_announced: bool = False
    wild_models: dict[PlayerId, PlayerId] = {}  # Wild Child -> role model
    infection_used: bool = False
    infect_target: PlayerId | None = None
    white_target: PlayerId | None = None

    def wolf_victim(self) -> PlayerId | None:
        """The pack's choice: most votes; on a tie, the first of the tied targets voted for.

        A Little Girl caught spying is eaten instead.
        """
        if self.caught_girl is not None:
            return self.caught_girl
        if not self.wolf_votes:
            return None
        counts = Counter(self.wolf_votes.values())
        top = max(counts.values())
        return next(t for t in self.wolf_votes.values() if counts[t] == top)


def word_count(text: str) -> int:
    return len(text.split())


def _text(description: str, limit: int) -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": limit * 12, "description": description}


class Werewolf(GamePlugin[WerewolfState]):
    id = "werewolf"
    name = "Werewolf"
    version = "1"
    min_players = MIN_PLAYERS
    max_players = MAX_PLAYERS
    turn_mode = TurnMode.SEQUENTIAL
    max_turns = MAX_NIGHTS * cycle_turns(MAX_PLAYERS)

    def __init__(self) -> None:
        self._roles = load_roles()

    # --- the prompt --------------------------------------------------------

    def prompt_version(self, settings: Mapping[str, Any] | None = None) -> str:
        """The prompt version of a match, recorded with it (see `prompt.py` next to this file)."""
        return prompt.version_of(settings)

    def rules(self, settings: Mapping[str, Any] | None = None) -> str:
        return prompt.rules_text(prompt.version_of(settings))

    def situation_summary(
        self, observation: Mapping[str, Any], settings: Mapping[str, Any] | None = None
    ) -> str | None:
        """A short text for the top of the turn's prompt; only version p2 has one."""
        version = prompt.version_of(settings)
        if version == "werewolf-p1":
            return None
        if version == "werewolf-p3":
            return prompt.situation_summary_v3(observation)
        return prompt.situation_summary(observation)

    # --- setup -------------------------------------------------------------

    def initial_state(
        self, players: Sequence[PlayerId], settings: Mapping[str, Any]
    ) -> WerewolfState:
        unknown = set(settings) - {
            "template",
            "roles",
            "roles_public",
            "captain",
            "language",
            "prompt_version",
        }
        if unknown:
            raise ValueError(f"Unknown settings for werewolf: {sorted(unknown)}")
        prompt.version_of(settings)
        language = settings.get("language", "de")
        if language not in LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}, got {language!r}")
        if "template" in settings and "roles" in settings:
            raise ValueError("Give either a template or roles, not both")
        count = len(players)
        template = settings.get("template", "classic" if "roles" not in settings else None)
        selection: dict[str, int] = {}
        if template == "random_balanced":
            pass  # drawn at setup from the match seed
        elif template is not None:
            selection = apply_template(template, count, roles=self._playable())
        else:
            selection = fill_selection(settings["roles"], count)
        if selection:
            problems = validate_selection(selection, count, self._roles)
            if problems:
                raise ValueError("; ".join(problem.message for problem in problems))
            missing = sorted(r for r in selection if r not in self._playable())
            if missing:
                raise ValueError(f"Roles not playable yet: {', '.join(missing)}")
        return WerewolfState(
            players=list(players),
            selection=selection,
            template=template,
            roles_public=bool(settings.get("roles_public", False)),
            alive=list(players),
            language=language,
            captain_enabled=bool(settings.get("captain", OPTIONS["captain"]["enabled"])),
            captain_weight=OPTIONS["captain"]["vote_weight"],
            successor_on_death=OPTIONS["captain"]["successor_on_death"],
        )

    def _playable(self) -> dict:
        """Roles whose every hook is implemented in abilities.py."""
        return {
            role_id: role
            for role_id, role in self._roles.items()
            if all(implemented(handler) for handler in role.hooks.values())
        }

    def setup(self, state: WerewolfState, ctx: TurnContext) -> None:
        selection = state.selection or apply_template(
            "random_balanced", len(state.players), ctx.rng("random_roles"), roles=self._playable()
        )
        dealt = assign_roles(selection, state.players, ctx.rng("roles"), self._roles)
        ctx.emit("roles_dealt", {"selection": selection}, visible_to=[])
        for player in state.players:
            ctx.emit(
                "role_assigned", {"player": player, "role": dealt[player]}, visible_to=[player]
            )
        pack = [p for p in state.players if self._roles[dealt[p]].hunts_with_wolves]
        ctx.emit("pack_revealed", {"wolves": pack}, visible_to=pack)
        if state.roles_public:
            ctx.emit("roles_in_play", {"selection": selection})
        self._start_night(state, ctx, 1)

    def _start_night(self, state: WerewolfState, ctx: TurnContext, night: int) -> None:
        ctx.emit("night_started", {"night": night})
        self._narrate(state, ctx, "night_falls", {"night": night})

    def _narrate(self, state: WerewolfState, ctx: TurnContext, key: str, data: dict) -> None:
        """A public narrator line from the template; a game master may retell it with a model."""
        text = narrate(key, data, state.language)
        ctx.emit("narration", {"key": key, "data": data, "text": text, "language": state.language})

    # --- turns -------------------------------------------------------------

    def active_players(self, state: WerewolfState) -> list[PlayerId]:
        return [state.queue[0].player] if state.queue and state.phase != "over" else []

    def get_tools(self, state: WerewolfState, player: PlayerId) -> list[ToolSpec]:
        if player not in self.active_players(state):
            return []
        step = state.queue[0]
        others = [p for p in state.alive if p != player]
        return self._step_tools(state, player, step, others) + self._lover_tools(state, player)

    def _lover_tools(self, state: WerewolfState, player: PlayerId) -> list[ToolSpec]:
        if player not in state.lovers or state.lover_talked:
            return []
        return [
            tool(
                "lover_chat",
                f"Whisper to your lover only (at most {MAX_SHORT_WORDS} words). Once per turn; "
                "it does not end your turn.",
                {"text": _text("What you tell your lover.", MAX_SHORT_WORDS)},
                required=["text"],
            )
        ]

    def _step_tools(
        self, state: WerewolfState, player: PlayerId, step: Step, others: list[PlayerId]
    ) -> list[ToolSpec]:
        if step.kind == "night":
            return NIGHT[step.ability].tools(state, player)
        if step.kind == "wolf":
            prey = [p for p in state.alive if p not in state.pack]
            tools = [
                tool(
                    "wolf_kill",
                    "Vote for tonight's victim. The pack's majority decides.",
                    {"target": target_schema(prey, "The player to attack.")},
                    required=["target"],
                )
            ]
            if state.wolf_messages.get(player, 0) < MAX_WOLF_MESSAGES:
                tools.insert(
                    0,
                    tool(
                        "wolf_chat",
                        f"Talk to the pack only (at most {MAX_WOLF_MESSAGES} messages a night, "
                        f"{MAX_SHORT_WORDS} words each). Your vote still follows.",
                        {"text": _text("What you tell the pack.", MAX_SHORT_WORDS)},
                        required=["text"],
                    ),
                )
            return tools
        if step.kind == "speak":
            return [
                tool(
                    "speak",
                    f"Your public speech in the discussion, at most {MAX_SPEECH_WORDS} words.",
                    {"text": _text("What you say to everyone.", MAX_SPEECH_WORDS)},
                    required=["text"],
                )
            ]
        if step.kind == "captain_vote":
            return [
                tool(
                    "elect_captain",
                    "Vote for the village captain. The captain's day vote counts double.",
                    {"target": target_schema(list(state.alive), "Your candidate.")},
                    required=["target"],
                )
            ]
        if step.kind == "pass_captaincy":
            return [
                tool(
                    "pass_captaincy",
                    "You are dying as captain: name the living player who takes over.",
                    {"target": target_schema(others, "The new captain.")},
                    required=["target"],
                )
            ]
        if step.kind == "vote":
            return [
                tool(
                    "vote",
                    "Vote publicly for the player to execute, or null to abstain. "
                    "The most votes decide; on a tie nobody dies.",
                    {
                        "target": target_schema([None, *others], "Your vote, or null."),
                        "reason": _text("Why, in a few words (optional).", MAX_SHORT_WORDS),
                    },
                    required=["target"],
                )
            ]
        return [
            tool(
                "hunter_shoot",
                "You are dying: take one living player with you.",
                {"target": target_schema(others, "The player you shoot.")},
                required=["target"],
            )
        ]

    def validate(self, state: WerewolfState, player: PlayerId, action: Action) -> str | None:
        args = action.arguments
        limits = {
            "speak": MAX_SPEECH_WORDS,
            "wolf_chat": MAX_SHORT_WORDS,
            "lover_chat": MAX_SHORT_WORDS,
            "vote": MAX_SHORT_WORDS,
        }
        text = args.get("reason") if action.tool == "vote" else args.get("text")
        if action.tool in limits and text is not None and word_count(text) > limits[action.tool]:
            return (
                f"Your text has {word_count(text)} words; say it in at most {limits[action.tool]}."
            )
        step = state.queue[0]
        if step.kind == "night" and action.tool != "lover_chat":
            return NIGHT[step.ability].validate(state, player, action)
        return None

    def apply_actions(
        self, state: WerewolfState, actions: Mapping[PlayerId, Action], ctx: TurnContext
    ) -> None:
        for player, action in actions.items():
            step = state.queue[0]
            args = action.arguments
            if action.tool == "wolf_chat":
                ctx.emit(MESSAGE, {"player": player, "text": args["text"]}, visible_to=state.pack)
                ctx.emit("wolf_talked", {"player": player}, visible_to=state.pack)
                continue  # the wolf still has to vote
            if action.tool == "lover_chat":
                ctx.emit(MESSAGE, {"player": player, "text": args["text"]}, visible_to=state.lovers)
                ctx.emit("lover_talked", {"player": player}, visible_to=state.lovers)
                continue  # the turn goes on
            if step.kind == "night":
                NIGHT[step.ability].apply(state, player, action, ctx)
            elif action.tool == "wolf_kill":
                ctx.emit(
                    "wolf_vote", {"player": player, "target": args["target"]}, visible_to=state.pack
                )
            elif action.tool == "speak":
                ctx.emit(MESSAGE, {"player": player, "text": args["text"]})
            elif action.tool == "vote":
                ctx.emit("vote_cast", {"player": player, "target": args["target"]})
                if args.get("reason"):
                    ctx.emit(MESSAGE, {"player": player, "text": args["reason"]})
            elif action.tool == "hunter_shoot":
                ctx.emit("hunter_shot", {"player": player, "target": args["target"]})
            elif action.tool == "elect_captain":
                ctx.emit("captain_vote", {"player": player, "target": args["target"]})
            elif action.tool == "pass_captaincy":
                ctx.emit("captain_passed", {"from": player, "to": args["target"]})
                self._narrate(state, ctx, "captain_passed", {"player": args["target"]})
            ctx.emit("step_done", {"player": player}, visible_to=[])
            if action.tool == "elect_captain" and not (
                state.queue and state.queue[0].kind == "captain_vote"
            ):
                self._elect_captain(state, ctx)
            if action.tool == "hunter_shoot":
                self._kill(state, ctx, [(args["target"], "hunter")])
        self.step(state, ctx)

    def step(self, state: WerewolfState, ctx: TurnContext) -> None:
        """Advance through everything that needs no decision until someone must act."""
        while not state.queue and state.phase != "over":
            if state.phase == "night":
                self._end_night(state, ctx)
            elif state.phase in ("morning", "dusk"):
                if self._check_winner(state, ctx):
                    return
                if state.phase == "morning":
                    order = list(state.alive)
                    start = ctx.rng("speaking_order", state.night).randrange(len(order))
                    ctx.emit(
                        "day_started", {"day": state.night, "order": order[start:] + order[:start]}
                    )
                elif state.night >= MAX_NIGHTS:
                    ctx.emit(
                        "game_over", {"winner": "nobody", "winners": [], "reason": "night_limit"}
                    )
                    return
                else:
                    self._start_night(state, ctx, state.night + 1)
            elif state.phase == "day":
                self._end_day(state, ctx)

    # --- night and day ------------------------------------------------------

    def _night_queue(self, state: WerewolfState) -> list[Step]:
        entries = []
        for seat, player in enumerate(state.players):
            if player not in state.alive:
                continue
            role = self._roles[state.roles[player]]
            handler = role.hooks.get("on_night")
            stripped = state.powers_lost and role.team == "village"
            if handler and role.night_order is not None and not stripped:
                ability = NIGHT[handler]
                if (not role.first_night_only or state.night == 1) and ability.acts_tonight(
                    state, player
                ):
                    entries.append(
                        (
                            role.night_order,
                            ability.sub_order,
                            seat,
                            Step(kind="night", player=player, ability=handler),
                        )
                    )
            if player in state.pack:
                entries.append((WOLF_NIGHT_ORDER, -1, seat, Step(kind="wolf", player=player)))
        return [step for *_, step in sorted(entries, key=lambda e: e[:3])]

    def _end_night(self, state: WerewolfState, ctx: TurnContext) -> None:
        deaths = []
        victim = state.wolf_victim()
        saved = victim in (state.healed, state.protected)
        if victim is not None and not saved and self._elder_survives(state, ctx, victim):
            saved = True
        infected = None
        if victim is not None and not saved and victim == state.infect_target:
            infected = victim
        elif victim is not None and not saved:
            cause = "caught_spying" if victim == state.caught_girl else "wolves"
            deaths.append((victim, cause))
        for target, cause in ((state.white_target, "white_wolf"), (state.poisoned, "poison")):
            if target and target in state.alive and all(target != p for p, _ in deaths):
                deaths.append((target, cause))
        ctx.emit("morning_started", {"night": state.night, "deaths": [p for p, _ in deaths]})
        if deaths:
            dead = [{"player": p, "role": state.roles[p]} for p, _ in deaths]
            self._narrate(state, ctx, "morning_deaths", {"deaths": dead})
        else:
            self._narrate(state, ctx, "morning_quiet", {})
        if infected is not None:
            ctx.emit("infected", {"player": infected}, visible_to=[*state.pack, infected])
        self._bear_growl(state, ctx, dead={p for p, _ in deaths})
        if state.marked is not None and state.marked not in {p for p, _ in deaths}:
            ctx.emit("raven_mark_announced", {"target": state.marked})
            self._narrate(state, ctx, "raven_mark", {"player": state.marked})
        self._kill(state, ctx, deaths)

    def _bear_growl(self, state: WerewolfState, ctx: TurnContext, dead: set) -> None:
        """The bear growls if a living wolf sits next to its tamer (the dead are skipped)."""
        living = [p for p in state.players if p in state.alive and p not in dead]
        for tamer in living:
            if not self._has(state, tamer, "on_morning", "bear_growl") or len(living) < 2:
                continue
            seat = living.index(tamer)
            neighbours = {living[seat - 1], living[(seat + 1) % len(living)]} - {tamer}
            if neighbours & set(state.pack):
                ctx.emit("bear_growled", {})
                self._narrate(state, ctx, "bear_growl", {})

    def _has(self, state: WerewolfState, player: PlayerId, hook: str, handler: str) -> bool:
        """Whether the player's role has this passive hook (village powers can be lost)."""
        role = self._roles[state.roles[player]]
        if state.powers_lost and role.team == "village" and handler != "lover_dies_of_grief":
            return False
        return role.hooks.get(hook) == handler

    def _elder_survives(self, state: WerewolfState, ctx: TurnContext, victim: PlayerId) -> bool:
        if victim in state.elder_hit or not self._has(
            state, victim, "on_wolf_attack", "elder_survives_first"
        ):
            return False
        ctx.emit("elder_survived", {"player": victim}, visible_to=[victim])
        return True

    def _elect_captain(self, state: WerewolfState, ctx: TurnContext) -> None:
        """Most votes win; a tie is broken by the match seed."""
        counts = Counter(state.captain_votes.values())
        top = max(counts.values())
        tied = [p for p in state.players if counts.get(p) == top]
        chosen = tied[0] if len(tied) == 1 else ctx.rng("captain_tie", state.day).choice(tied)
        ctx.emit("captain_elected", {"player": chosen, "votes": dict(counts)})
        self._narrate(state, ctx, "captain_elected", {"player": chosen})

    def _end_day(self, state: WerewolfState, ctx: TurnContext) -> None:
        counts: Counter[PlayerId] = Counter()
        for voter, target in state.day_votes.items():
            if target is not None:
                counts[target] += state.captain_weight if voter == state.captain else 1
        if state.marked in state.alive and state.mark_announced:
            counts[state.marked] += RAVEN_VOTES
        top = max(counts.values(), default=0)
        leaders = [p for p, n in counts.items() if n == top]
        executed = leaders[0] if top > 0 and len(leaders) == 1 else None
        cause = "executed"
        if top > 0 and len(leaders) > 1:
            scapegoat = next(
                (p for p in state.alive if self._has(state, p, "on_vote_tie", "scapegoat_dies")),
                None,
            )
            if scapegoat is not None:
                executed, cause = scapegoat, "scapegoat"
        ctx.emit("vote_result", {"day": state.day, "counts": dict(counts), "executed": executed})
        if executed is None:
            self._narrate(state, ctx, "no_execution", {})
            return
        role = state.roles[executed]
        if cause == "executed" and self._has(state, executed, "on_execution", "idiot_survives"):
            ctx.emit("idiot_revealed", {"player": executed, "role": role})
            self._narrate(state, ctx, "idiot_spared", {"player": executed})
            return
        key = "scapegoat" if cause == "scapegoat" else "execution"
        self._narrate(state, ctx, key, {"player": executed, "role": role})
        self._kill(state, ctx, [(executed, cause)])
        if cause == "executed" and self._has(
            state, executed, "on_execution", "elder_strips_powers"
        ):
            ctx.emit("powers_lost", {"elder": executed})
            self._narrate(state, ctx, "powers_lost", {"player": executed})

    def _kill(
        self, state: WerewolfState, ctx: TurnContext, deaths: list[tuple[PlayerId, str]]
    ) -> None:
        """Announce deaths; their effects (the Hunter's shot) are queued by apply_event."""
        pending = list(deaths)
        while pending:
            player, cause = pending.pop(0)
            if player not in state.alive:
                continue
            ctx.emit("player_died", {"player": player, "cause": cause, "role": state.roles[player]})
            for child, model in state.wild_models.items():
                turns = self._has(state, child, "on_model_death", "wild_child_turns_wolf")
                if model == player and child in state.alive and child not in state.pack and turns:
                    ctx.emit("joined_pack", {"player": child}, visible_to=[*state.pack, child])
            if player in state.lovers:
                partner = next(p for p in state.lovers if p != player)
                if partner in state.alive:
                    pending.insert(0, (partner, "grief"))
                    self._narrate(state, ctx, "grief", {"player": partner, "lover": player})

    def _check_winner(self, state: WerewolfState, ctx: TurnContext) -> bool:
        # The White Werewolf hunts with the pack but plays alone.
        loners = [p for p in state.players if self._roles[state.roles[p]].team == "solo"]
        pack = [p for p in state.alive if p in state.pack and p not in loners]
        others = [p for p in state.alive if p not in pack]
        hunters = [p for p in state.alive if p in state.pack]
        # Lovers across the teams (a wolf and a non-wolf) play for themselves.
        mixed = state.lovers if len({p in state.pack for p in state.lovers}) == 2 else []
        if not state.alive:
            outcome = ("nobody", [])
        elif mixed and set(state.alive) == set(mixed):
            outcome = ("lovers", list(mixed))
        elif len(state.alive) == 1 and state.alive[0] in loners:
            outcome = ("white_wolf", list(state.alive))
        elif not hunters:
            outcome = (
                "village",
                [p for p in state.players if p not in state.pack and p not in mixed],
            )
        elif pack and len(pack) >= len(others):
            outcome = (
                "wolves",
                [p for p in state.players if p in state.pack and p not in mixed + loners],
            )
        else:
            return False
        ctx.emit("game_over", {"winner": outcome[0], "winners": outcome[1]})
        self._narrate(state, ctx, "game_over", {"winner": outcome[0]})
        return True

    # --- event application ------------------------------------------------

    def apply_event(self, state: WerewolfState, event: Event) -> None:
        if event.type == MESSAGE:
            return
        data = event.data
        match event.type:
            case "roles_dealt":
                state.selection = dict(data["selection"])
            case "role_assigned":
                state.roles[data["player"]] = data["role"]
            case "pack_revealed":
                state.pack = list(data["wolves"])
            case "roles_in_play":
                pass
            case "night_started":
                state.night = data["night"]
                state.phase = "night"
                state.wolf_messages = {}
                state.wolf_votes = {}
                state.healed = None
                state.poisoned = None
                state.protected = None
                state.caught_girl = None
                state.infect_target = None
                state.white_target = None
                state.queue = self._night_queue(state)
            case "wolf_talked":
                state.wolf_messages[data["player"]] = state.wolf_messages.get(data["player"], 0) + 1
            case "wolf_vote":
                state.wolf_votes[data["player"]] = data["target"]
            case "seer_inspected":
                state.seer_results.setdefault(data["player"], {})[data["target"]] = data["role"]
            case "witch_acted":
                if data["healed"]:
                    state.potions["heal"] = False
                    state.healed = data["healed"]
                if data["poisoned"]:
                    state.potions["poison"] = False
                    state.poisoned = data["poisoned"]
            case "step_done":
                if not state.queue or state.queue[0].player != data["player"]:
                    raise ValueError(f"step_done for {data['player']} out of turn")
                state.queue.pop(0)
                state.lover_talked = False
            case "morning_started":
                state.phase = "morning"
            case "player_died":
                player = data["player"]
                state.alive.remove(player)
                state.revealed[player] = data["role"]
                if player == state.captain:
                    if state.successor_on_death and state.alive:
                        state.queue.insert(0, Step(kind="pass_captaincy", player=player))
                    else:
                        state.captain = None
                if self._has(state, player, "on_death", "hunter_shoot") and state.alive:
                    state.queue.insert(0, Step(kind="hunter", player=player))
            case "hunter_shot" | "narration" | "lovers_linked" | "spied":
                pass
            case "love_revealed":
                state.lovers = list(data["lovers"])
            case "lover_talked":
                state.lover_talked = True
            case "protected":
                state.protected = data["target"]
                state.last_protected = data["target"]
            case "raven_chose":
                state.marked = data["target"]
                state.mark_announced = False
            case "raven_mark_announced":
                state.mark_announced = True
            case "model_chosen":
                state.wild_models[data["player"]] = data["model"]
            case "infection_chosen":
                state.infection_used = True
                state.infect_target = data["target"]
            case "white_wolf_chose":
                state.white_target = data["target"]
            case "infected" | "joined_pack":
                if data["player"] not in state.pack:
                    state.pack.append(data["player"])
            case "bear_growled":
                pass
            case "girl_caught":
                state.caught_girl = data["player"]
            case "elder_survived":
                state.elder_hit.append(data["player"])
            case "idiot_revealed":
                state.revealed[data["player"]] = data["role"]
                state.no_vote.append(data["player"])
            case "powers_lost":
                state.powers_lost = True
            case "captain_vote":
                state.captain_votes[data["player"]] = data["target"]
            case "captain_elected":
                state.captain = data["player"]
            case "captain_passed":
                state.captain = data["to"]
            case "day_started":
                state.day = data["day"]
                state.phase = "day"
                state.day_votes = {}
                state.speaking_order = list(data["order"])
                speeches = [Step(kind="speak", player=p) for p in data["order"]] * DISCUSSION_ROUNDS
                living = [p for p in state.players if p in state.alive]
                votes = [Step(kind="vote", player=p) for p in living if p not in state.no_vote]
                election = []
                if state.captain_enabled and data["day"] == 1:
                    election = [Step(kind="captain_vote", player=p) for p in living]
                state.queue = election + speeches + votes
            case "vote_cast":
                state.day_votes[data["player"]] = data["target"]
            case "vote_result":
                state.phase = "dusk"
                state.marked = None
                state.mark_announced = False
            case "game_over":
                state.phase = "over"
                state.winner = data["winner"]
                state.winners = list(data["winners"])
                state.queue = []
            case unknown:
                raise ValueError(f"Unknown werewolf event: {unknown}")

    # --- views -------------------------------------------------------------

    def get_observation(self, state: WerewolfState, player: PlayerId) -> dict[str, Any]:
        role = self._roles[state.roles[player]] if player in state.roles else None
        step = state.queue[0] if state.queue and state.queue[0].player == player else None
        observation: dict[str, Any] = {
            "you": player,
            "role": (
                {"id": role.id, "name": role.name, "team": role.team, "rules": role.rules_snippet}
                if role
                else None
            ),
            "phase": state.phase,
            "night": state.night,
            "day": state.day,
            "alive": list(state.alive),
            "dead": [
                {"player": p, "role": r} for p, r in state.revealed.items() if p not in state.alive
            ],
            "revealed_alive": [
                {"player": p, "role": r} for p, r in state.revealed.items() if p in state.alive
            ],
            "your_turn": step is not None,
            "step": step.kind if step else None,
            "speaking_order": list(state.speaking_order),
            "votes_today": dict(state.day_votes),
            "captain": state.captain,
            "language": state.language,
        }
        if player in state.pack:
            observation["pack"] = list(state.pack)
            observation["wolf_votes"] = dict(state.wolf_votes)
        if player in state.seer_results:
            observation["seer_results"] = dict(state.seer_results[player])
        if role and role.hooks.get("on_night") == "witch_potions":
            observation["potions"] = dict(state.potions)
            if step is not None and step.kind == "night":
                observation["wolf_victim"] = state.wolf_victim()
        if player in state.lovers:
            observation["lovers"] = list(state.lovers)
        if role and role.hooks.get("on_night") == "protector_guard":
            observation["protected_last_night"] = state.last_protected
        if player in state.no_vote:
            observation["may_vote"] = False
        if state.powers_lost:
            observation["village_powers_lost"] = True
        if state.mark_announced and state.marked:
            observation["raven_mark"] = state.marked
        if player in state.wild_models:
            observation["role_model"] = state.wild_models[player]
        if role and role.hooks.get("on_night") == "prime_wolf_infect":
            observation["infection_used"] = state.infection_used
        if state.roles_public:
            observation["roles_in_play"] = dict(state.selection)
        return observation

    def render_spec(self, state: WerewolfState) -> dict[str, Any]:
        """What a spectator view draws: the circle with every role (spectators may see all).

        Not part of the plugin interface yet (D-046); the UI will define it in phase 5.
        """
        return {
            "layout": "player_circle",
            "phase": state.phase,
            "night": state.night,
            "day": state.day,
            "seats": [
                {"player": p, "role": state.roles.get(p), "alive": p in state.alive}
                for p in state.players
            ],
            "turn": state.queue[0].player if state.queue else None,
        }

    # --- end ---------------------------------------------------------------

    def is_over(self, state: WerewolfState) -> bool:
        return state.phase == "over"

    def results(self, state: WerewolfState) -> list[Placement]:
        """The winning side shares rank 1, everyone else shares the next rank."""
        losers_rank = len(state.winners) + 1
        return [
            Placement(player=p, rank=1 if p in state.winners else losers_rank)
            for p in state.players
        ]

    def random_action(
        self, observation: Mapping[str, Any], tools: Sequence[ToolSpec], rng: random.Random
    ) -> Action:
        """Any final action (chat only sometimes) with random allowed arguments."""
        final = [t for t in tools if t.name not in ("wolf_chat", "lover_chat")]
        chosen = rng.choice(tools) if not final or rng.random() < 0.1 else rng.choice(final)
        arguments = {}
        for name, schema in chosen.parameters["properties"].items():
            if "enum" in schema:
                arguments[name] = rng.choice(schema["enum"])
            elif schema.get("type") == "string" and name in chosen.parameters["required"]:
                arguments[name] = "I have nothing to add."
        return Action(tool=chosen.name, arguments=arguments)
