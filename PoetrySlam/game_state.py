from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set

import poetry_slam as game
from bot_logic import pick_bot_word

TURN_SECONDS = 10
BOT_ACTION_MIN = 0.0
BOT_ACTION_MAX = 0.0
MAX_PLAYERS = 5


@dataclass
class PlayerInfo:
    player_id: str
    kind: str
    label: str
    avatar_class: str
    score: int = 0


@dataclass
class GameState:
    prompt: str
    players: Dict[str, PlayerInfo]
    turn_order: List[str]
    turn: str
    deadline_mono: float
    bot_action_mono: float | None
    paused: bool
    paused_time_left: float
    paused_bot_delay: float | None
    pending_bot_word: str
    pending_bot_correct: bool
    pending_bot_actor: str
    last_event: str
    last_actor: str
    last_result: str
    last_player_word: str
    last_bot_word: str
    last_bot_actor: str
    last_word_actor: str
    out_players: Set[str] = field(default_factory=set)
    used_words: Set[str] = field(default_factory=set)
    used_keys: Set[str] = field(default_factory=set)
    live_inputs: Dict[str, str] = field(default_factory=dict)
    round_turns: int = 0
    round_id: int = 0
    round_rhyme_count: int = 0
    game_id: int = 0


class GameEngine:
    def __init__(self) -> None:
        self.max_players = MAX_PLAYERS
        self.game_id = 0
        self.rhyme_attempts: list[dict] = []
        self.rhyme_attempt_keys: set[tuple[str, str]] = set()
        self.state = self._new_state()

    def setup_room(self, bot_count: int) -> None:
        self.state = self._new_state()
        for _ in range(self._normalize_bot_count(bot_count)):
            self.add_player(kind="bot")

    def set_bot_count(self, bot_count: int) -> None:
        state = self.state
        human_count = len([p for p in state.players.values() if p.kind == "human"])
        target = min(self._normalize_bot_count(bot_count), self.max_players - human_count)
        bots = [pid for pid in state.turn_order if pid.startswith("bot")]
        if len(bots) == target:
            return
        if len(bots) < target:
            for _ in range(target - len(bots)):
                self.add_player(kind="bot")
            return
        to_remove = bots[target:]
        for pid in to_remove:
            state.turn_order.remove(pid)
            state.players.pop(pid, None)
            state.out_players.discard(pid)
        if state.turn in to_remove and state.turn_order:
            self._start_turn(state, state.turn_order[0])

    def _new_state(self) -> GameState:
        self.game_id += 1
        state = GameState(
            prompt=game.pick_prompt(),
            players={},
            turn_order=[],
            turn="",
            deadline_mono=0.0,
            bot_action_mono=None,
            paused=False,
            paused_time_left=0.0,
            paused_bot_delay=None,
            pending_bot_word="",
            pending_bot_correct=False,
            pending_bot_actor="",
            last_event="New game started.",
            last_actor="system",
            last_result="info",
            last_player_word="",
            last_bot_word="",
            last_bot_actor="",
            last_word_actor="system",
            out_players=set(),
            used_words=set(),
            used_keys=set(),
            live_inputs={},
            round_turns=0,
            round_id=0,
            round_rhyme_count=0,
            game_id=self.game_id,
        )
        state.used_words.add(state.prompt.lower())
        state.used_keys.add(self._word_key(state.prompt))
        return state

    def new_game(self) -> None:
        state = self.state
        existing = [(pid, info.kind, info.label, info.avatar_class) for pid, info in state.players.items()]
        order = list(state.turn_order)
        self.state = self._new_state()
        for pid in order:
            info = next((p for p in existing if p[0] == pid), None)
            if info:
                self._add_existing_player(*info)
        if self.state.turn_order:
            self._start_turn(self.state, self.state.turn_order[0])

    def bot_count(self) -> int:
        return len([p for p in self.state.players.values() if p.kind == "bot"])

    def player_count(self) -> int:
        return len(self.state.players)

    def add_player(self, kind: str, name: str | None = None) -> str:
        state = self.state
        if len(state.turn_order) >= self.max_players:
            raise ValueError("Room is full")
        if kind == "bot":
            bot_index = 1 + len([p for p in state.players.values() if p.kind == "bot"])
            player_id = f"bot{bot_index}"
            label = f"BOT {chr(64 + bot_index)}"
            avatar_class = player_id
        else:
            human_index = 1 + len([p for p in state.players.values() if p.kind == "human"])
            player_id = f"p{human_index}"
            label = self._normalize_name(name) or f"PLAYER {human_index}"
            avatar_class = "player"
        state.players[player_id] = PlayerInfo(
            player_id=player_id,
            kind=kind,
            label=label,
            avatar_class=avatar_class,
        )
        state.turn_order.append(player_id)
        if not state.turn:
            self._start_turn(state, player_id)
        return player_id

    def set_player_name(self, player_id: str, name: str | None) -> None:
        normalized = self._normalize_name(name)
        if not normalized:
            return
        if player_id in self.state.players:
            self.state.players[player_id].label = normalized

    def _add_existing_player(self, player_id: str, kind: str, label: str, avatar_class: str) -> None:
        state = self.state
        state.players[player_id] = PlayerInfo(
            player_id=player_id,
            kind=kind,
            label=label,
            avatar_class=avatar_class,
        )
        state.turn_order.append(player_id)

    def payload(self, self_id: str | None = None) -> dict:
        state = self.state
        payload = {
            "prompt": state.prompt,
            "turn": state.turn,
            "time_left": self._time_left_ratio(state),
            "last_event": state.last_event,
            "last_actor": state.last_actor,
            "last_result": state.last_result,
            "player_word": state.last_player_word,
            "bot_word": state.last_bot_word,
            "bot_actor": state.last_bot_actor,
            "last_word_actor": state.last_word_actor,
            "bot_pending": bool(state.pending_bot_word),
            "round_id": state.round_id,
            "remaining_rhymes": max(0, state.round_rhyme_count - len(state.used_keys)),
            "paused": state.paused,
            "out_players": sorted(state.out_players),
            "game_id": state.game_id,
            "rhyme_part_display": game.rhyming_part_display(state.prompt),
            "self_id": self_id,
            "live_input": state.live_inputs.get(state.turn, ""),
        }
        payload["players"] = [
            {
                "id": pid,
                "score": state.players[pid].score,
                "out": pid in state.out_players,
                "label": state.players[pid].label,
                "card_class": self._player_card_class(idx),
                "avatar_class": state.players[pid].avatar_class,
                "is_self": pid == self_id,
            }
            for idx, pid in enumerate(state.turn_order)
        ]
        return payload

    def rhyme_attempts_payload(self) -> dict:
        return {"attempts": list(self.rhyme_attempts)}

    def confirm_rhyme_attempt(self, prompt: str, guess: str, accepted: bool) -> None:
        key = (prompt.lower(), guess.lower())
        if key in self.rhyme_attempt_keys:
            self.rhyme_attempt_keys.remove(key)
            self.rhyme_attempts = [
                attempt
                for attempt in self.rhyme_attempts
                if not (attempt.get("prompt") == key[0] and attempt.get("guess") == key[1])
            ]
        if accepted:
            game.add_custom_rhyme(guess, prompt)

    def handle_guess(self, data: dict, *, actor: str) -> None:
        state = self.state
        guess = (data.get("guess") or "").strip()
        difficulty = data.get("difficulty") or "Medium"

        settings = game.RhymeSettings(
            allow_trailing_consonant_cluster=bool(data.get("allow_trailing_consonant_cluster")),
            allow_final_consonant_class_substitution=bool(
                data.get("allow_final_consonant_class_substitution")
            ),
            coda_ignore_voicing=bool(data.get("coda_ignore_voicing")),
            coda_same_manner=bool(data.get("coda_same_manner")),
            coda_same_place=bool(data.get("coda_same_place")),
            allow_vowel_match_only=bool(data.get("allow_vowel_match_only")),
            allow_near_vowel_substitution=bool(data.get("allow_near_vowel_substitution")),
            near_vowel_tense_lax_pairs=bool(data.get("near_vowel_tense_lax_pairs")),
            near_vowel_short_front_bucket=bool(data.get("near_vowel_short_front_bucket")),
        )
        slant_bonus_enabled = bool(data.get("bonus_slant_rhyme"))
        any_slant_enabled = any(
            [
                settings.allow_trailing_consonant_cluster,
                settings.allow_final_consonant_class_substitution,
                settings.coda_ignore_voicing,
                settings.coda_same_manner,
                settings.coda_same_place,
                settings.allow_vowel_match_only,
                settings.allow_near_vowel_substitution,
                settings.near_vowel_tense_lax_pairs,
                settings.near_vowel_short_front_bucket,
            ]
        )

        self.process_timers(difficulty)
        if state.paused or state.turn != actor:
            return

        if not guess:
            self._set_event(state, actor, ["Please enter a word."], "bad")
            return

        if guess.strip().lower() == "/suicide":
            winner = self._next_turn(state.turn)
            self._award_points(state, winner, state.round_turns)
            self._set_event(state, winner, [f"Round over. +{state.round_turns} points"], "good")
            self._start_round(state, winner)
            return

        normalized = guess.lower()
        key = self._word_key(normalized)
        if key in state.used_keys:
            self._set_event(state, actor, ["Already used"], "bad")
            return

        res = game.judge_guess(state.prompt, guess, settings=settings)
        state.last_player_word = guess
        if res.status == game.GuessStatus.QUIT_COMMAND:
            self._set_event(state, actor, ["You quit the game. Starting a new match."], "info")
            self.new_game()
            return

        if res.status == game.GuessStatus.CORRECT:
            state.live_inputs[actor] = ""
            bonus = game.syllable_match_bonus(state.prompt, guess)
            if slant_bonus_enabled and any_slant_enabled and not game.words_rhyme(state.prompt, guess):
                bonus += 1
            if bonus:
                self._award_points(state, actor, bonus)
                self._set_event(state, actor, [f"Correct! +{bonus} bonus"], "good")
            else:
                self._set_event(state, actor, ["Correct!"], "good")
            state.used_words.add(normalized)
            state.used_keys.add(key)
            state.round_turns += 1
            state.prompt = normalized
            state.last_word_actor = actor
            self._advance_turn(state)
            return

        if res.status == game.GuessStatus.NOT_A_RHYME:
            message = "Not a rhyme"
        elif res.status == game.GuessStatus.VALID_ENGLISH_MISSING_CMU:
            self._track_rhyme_attempt(state.prompt, guess)
            message = "Not in rhyming dictionary"
        elif res.status == game.GuessStatus.NOT_RECOGNIZED_ENGLISH:
            message = "Not a valid word"
        elif res.status == game.GuessStatus.NOT_PLAUSIBLE_TOKEN:
            message = "Not a valid word"
        elif res.status == game.GuessStatus.SAME_AS_PROMPT:
            message = "Need a different word"
        else:
            message = "Try again"
        self._set_event(state, actor, [message], "bad")
        if res.status in (
            game.GuessStatus.NOT_A_RHYME,
            game.GuessStatus.VALID_ENGLISH_MISSING_CMU,
            game.GuessStatus.NOT_RECOGNIZED_ENGLISH,
            game.GuessStatus.NOT_PLAUSIBLE_TOKEN,
            game.GuessStatus.SAME_AS_PROMPT,
        ):
            state.live_inputs[actor] = ""

    def handle_bot_commit(self) -> None:
        state = self.state
        if not self._is_bot(state.turn) or not state.pending_bot_word:
            return

        if state.pending_bot_correct:
            state.live_inputs[state.pending_bot_actor] = ""
            bonus = game.syllable_match_bonus(state.prompt, state.pending_bot_word)
            state.used_words.add(state.pending_bot_word.lower())
            state.used_keys.add(self._word_key(state.pending_bot_word))
            state.round_turns += 1
            if bonus:
                self._award_points(state, state.pending_bot_actor, bonus)
                self._set_event(state, state.pending_bot_actor, [f"Correct! +{bonus} bonus"], "good")
            else:
                self._set_event(state, state.pending_bot_actor, ["Correct!"], "good")
            state.prompt = state.pending_bot_word.lower()
            state.last_word_actor = state.pending_bot_actor
            state.pending_bot_word = ""
            state.pending_bot_correct = False
            state.pending_bot_actor = ""
            self._advance_turn(state)
            return

        self._set_event(state, state.pending_bot_actor or "bot1", ["Not a rhyme"], "bad")
        if state.pending_bot_actor:
            state.live_inputs[state.pending_bot_actor] = ""
        state.pending_bot_word = ""
        state.pending_bot_correct = False
        state.pending_bot_actor = ""
        if time.monotonic() < state.deadline_mono - 0.3:
            delay = random.uniform(0.8, 2.2)
            state.bot_action_mono = min(state.deadline_mono - 0.2, time.monotonic() + delay)

    def process_timers(self, difficulty: str) -> None:
        state = self.state
        if state.paused:
            return
        now = time.monotonic()
        if now >= state.deadline_mono:
            self._set_event(state, state.turn, ["Time ran out."], "bad")
            state.pending_bot_word = ""
            state.pending_bot_correct = False
            state.pending_bot_actor = ""
            if state.turn:
                state.live_inputs[state.turn] = ""
            self._mark_out(state, state.turn)
            self._handle_after_out(state)
            return

        if self._is_bot(state.turn) and state.bot_action_mono is not None and now >= state.bot_action_mono:
            available = [
                w
                for w in game.accepted_words(state.prompt)
                if self._word_key(w) not in state.used_keys
            ]
            if not available:
                state.pending_bot_word = ""
                state.pending_bot_correct = False
                state.pending_bot_actor = ""
                state.bot_action_mono = None
                self._set_event(state, state.turn, ["No rhymes left."], "bad")
                return

            bot_word, bot_correct = pick_bot_word(available, difficulty)
            if bot_word:
                bot_word = bot_word.lower()
            if bot_word and self._word_key(bot_word) in state.used_keys:
                bot_correct = False
            state.pending_bot_word = bot_word or ""
            state.pending_bot_correct = bot_correct
            state.pending_bot_actor = state.turn
            state.last_bot_word = bot_word or ""
            state.last_bot_actor = state.turn
            state.bot_action_mono = None

    def toggle_pause(self) -> None:
        state = self.state
        if state.paused:
            self._resume(state)
        else:
            self._pause(state)

    def _start_turn(self, state: GameState, turn: str) -> None:
        now = time.monotonic()
        state.turn = turn
        state.deadline_mono = now + TURN_SECONDS
        state.bot_action_mono = None
        if turn:
            state.live_inputs[turn] = ""
        if self._is_bot(turn):
            delay = random.uniform(BOT_ACTION_MIN, BOT_ACTION_MAX)
            state.bot_action_mono = min(state.deadline_mono - 0.2, now + delay)
            state.last_bot_word = ""
            state.last_bot_actor = ""
        state.paused = False
        state.paused_time_left = 0.0
        state.paused_bot_delay = None

    def _advance_turn(self, state: GameState) -> None:
        self._start_turn(state, self._next_turn(state.turn))

    def _start_round(self, state: GameState, starting_turn: str) -> None:
        state.prompt = game.pick_prompt()
        state.used_words = set()
        state.used_keys = set()
        state.used_words.add(state.prompt.lower())
        state.used_keys.add(self._word_key(state.prompt))
        state.out_players = set()
        state.round_turns = 0
        state.last_player_word = ""
        state.last_bot_word = ""
        state.pending_bot_word = ""
        state.pending_bot_correct = False
        state.pending_bot_actor = ""
        state.last_bot_actor = ""
        state.live_inputs = {}
        state.round_id += 1
        state.round_rhyme_count = len(game.accepted_words(state.prompt))
        state.last_word_actor = "system"
        self._start_turn(state, starting_turn)

    def _set_event(self, state: GameState, actor: str, lines: List[str], result: str) -> None:
        entry = "\n".join(lines).strip()
        if entry:
            state.last_event = entry
            state.last_actor = actor
            state.last_result = result

    def _award_points(self, state: GameState, actor: str, points: int) -> None:
        if points <= 0:
            return
        if actor in state.players:
            state.players[actor].score += points

    def _next_turn(self, turn: str) -> str:
        active = self._active_turns(self.state)
        if not active:
            return ""
        try:
            start_idx = active.index(turn)
        except ValueError:
            start_idx = -1
        for offset in range(1, len(active) + 1):
            cand = active[(start_idx + offset) % len(active)]
            if cand not in self.state.out_players:
                return cand
        return active[0]

    def _time_left_ratio(self, state: GameState) -> float:
        if state.paused:
            remaining = max(0.0, state.paused_time_left)
        else:
            remaining = max(0.0, state.deadline_mono - time.monotonic())
        return min(1.0, remaining / TURN_SECONDS)

    def _word_key(self, word: str) -> str:
        w = (word or "").strip().lower()
        for suffix in ("ing", "ed", "es", "s"):
            if w.endswith(suffix) and len(w) > len(suffix) + 2:
                return w[: -len(suffix)]
        return w

    def _active_turns(self, state: GameState) -> list[str]:
        return list(state.turn_order)

    def _is_bot(self, player_id: str) -> bool:
        return player_id in self.state.players and self.state.players[player_id].kind == "bot"

    def _normalize_bot_count(self, value: int | str) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 1
        return max(0, min(self.max_players, count))

    def _normalize_name(self, value: str | None) -> str:
        if not value:
            return ""
        return value.strip()[:15]

    def update_live_input(self, actor: str, text: str) -> None:
        if not actor or actor not in self.state.players:
            return
        clean = (text or "")
        self.state.live_inputs[actor] = clean[:40]

    def _track_rhyme_attempt(self, prompt: str, guess: str) -> None:
        p = (prompt or "").strip().lower()
        g = (guess or "").strip().lower()
        if not p or not g:
            return
        key = (p, g)
        if key in self.rhyme_attempt_keys:
            return
        self.rhyme_attempt_keys.add(key)
        self.rhyme_attempts.append({"prompt": p, "guess": g})

    def _eligible_turns(self, state: GameState) -> list[str]:
        return [t for t in self._active_turns(state) if t not in state.out_players]

    def _mark_out(self, state: GameState, actor: str) -> None:
        if actor:
            state.out_players.add(actor)

    def _handle_after_out(self, state: GameState) -> None:
        eligible = self._eligible_turns(state)
        if not eligible:
            winner = state.last_word_actor if state.last_word_actor != "system" else state.turn
            self._award_points(state, winner, state.round_turns)
            self._set_event(state, winner, [f"Round over. +{state.round_turns} points"], "good")
            self._start_round(state, winner)
            return
        if len(eligible) == 1:
            winner = eligible[0]
            self._award_points(state, winner, state.round_turns)
            self._set_event(state, winner, [f"Round over. +{state.round_turns} points"], "good")
            self._start_round(state, winner)
            return
        if state.turn in state.out_players:
            self._start_turn(state, self._next_turn(state.turn))

    def _pause(self, state: GameState) -> None:
        if state.paused:
            return
        now = time.monotonic()
        state.paused = True
        state.paused_time_left = max(0.0, state.deadline_mono - now)
        if state.bot_action_mono is not None:
            state.paused_bot_delay = max(0.0, state.bot_action_mono - now)
        else:
            state.paused_bot_delay = None
        state.bot_action_mono = None

    def _resume(self, state: GameState) -> None:
        if not state.paused:
            return
        now = time.monotonic()
        state.paused = False
        state.deadline_mono = now + max(0.0, state.paused_time_left)
        if state.paused_bot_delay is not None:
            state.bot_action_mono = now + max(0.0, state.paused_bot_delay)
        else:
            state.bot_action_mono = None
        state.paused_time_left = 0.0
        state.paused_bot_delay = None

    def _player_card_class(self, idx: int) -> str:
        classes = ["player-one", "player-two", "player-three", "player-four", "player-five"]
        return classes[idx] if idx < len(classes) else classes[-1]
