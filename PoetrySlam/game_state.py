from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import List, Set

import poetry_slam as game
from bot_logic import pick_bot_word

TURN_SECONDS = 10
BOT_ACTION_MIN = 0.0
BOT_ACTION_MAX = 0.0

TURN_ORDER = ["player", "bot1", "bot2", "bot3", "bot4"]
BOT_IDS = [t for t in TURN_ORDER if t != "player"]


@dataclass
class GameState:
    prompt: str
    player_score: int
    bot1_score: int
    bot2_score: int
    bot3_score: int
    bot4_score: int
    bot_count: int
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
    used_words: Set[str] = field(default_factory=set)
    used_keys: Set[str] = field(default_factory=set)
    round_turns: int = 0
    round_id: int = 0
    round_rhyme_count: int = 0


class GameEngine:
    def __init__(self) -> None:
        self.bot_count = 1
        self.rhyme_attempts: list[dict] = []
        self.rhyme_attempt_keys: set[tuple[str, str]] = set()
        self.state = self._new_state()

    def _new_state(self, bot_count: int | None = None) -> GameState:
        count = self._normalize_bot_count(bot_count if bot_count is not None else self.bot_count)
        self.bot_count = count
        state = GameState(
            prompt=game.pick_prompt(),
            player_score=0,
            bot1_score=0,
            bot2_score=0,
            bot3_score=0,
            bot4_score=0,
            bot_count=count,
            turn="player",
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
            used_words=set(),
            used_keys=set(),
            round_turns=0,
            round_id=0,
            round_rhyme_count=0,
        )
        self._start_turn(state, "player")
        return state

    def new_game(self, bot_count: int | None = None) -> None:
        self.state = self._new_state(bot_count)

    def set_bot_count(self, bot_count: int) -> None:
        state = self.state
        count = self._normalize_bot_count(bot_count)
        self.bot_count = count
        if state.bot_count == count:
            return
        state.bot_count = count
        active_turns = self._active_turns(state)
        if state.turn not in active_turns:
            if state.paused:
                state.turn = "player"
                state.paused_time_left = TURN_SECONDS
                state.paused_bot_delay = None
            else:
                self._start_turn(state, "player")
        if state.pending_bot_actor and state.pending_bot_actor not in active_turns:
            state.pending_bot_word = ""
            state.pending_bot_correct = False
            state.pending_bot_actor = ""
            state.last_bot_word = ""
            state.last_bot_actor = ""

    def payload(self) -> dict:
        state = self.state
        return {
            "prompt": state.prompt,
            "turn": state.turn,
            "time_left": self._time_left_ratio(state),
            "player_score": state.player_score,
            "bot1_score": state.bot1_score,
            "bot2_score": state.bot2_score,
            "bot3_score": state.bot3_score,
            "bot4_score": state.bot4_score,
            "bot_count": state.bot_count,
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
        }

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

    def handle_guess(self, data: dict) -> None:
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

        self.process_timers(difficulty)
        if state.paused:
            return
        if state.turn != "player":
            return

        if not guess:
            self._set_event(state, "player", ["Please enter a word."], "bad")
            return

        if guess.strip().lower() == "/suicide":
            winner = self._next_turn("player")
            self._award_points(state, winner, state.round_turns)
            self._set_event(state, winner, [f"Round over. +{state.round_turns} points"], "good")
            self._start_round(state, winner)
            return

        normalized = guess.lower()
        key = self._word_key(normalized)
        if key in state.used_keys:
            self._set_event(state, "player", ["Already used"], "bad")
            return

        res = game.judge_guess(state.prompt, guess, settings=settings)
        state.last_player_word = guess
        if res.status == game.GuessStatus.QUIT_COMMAND:
            self._set_event(state, "player", ["You quit the game. Starting a new match."], "info")
            self.new_game()
            return

        if res.status == game.GuessStatus.CORRECT:
            bonus = game.syllable_match_bonus(state.prompt, guess)
            if bonus:
                self._award_points(state, "player", bonus)
                self._set_event(state, "player", [f"Correct! +{bonus} bonus"], "good")
            else:
                self._set_event(state, "player", ["Correct!"], "good")
            state.used_words.add(normalized)
            state.used_keys.add(key)
            state.round_turns += 1
            state.prompt = normalized
            state.last_word_actor = "player"
            self._advance_turn(state)
            return

        if res.status == game.GuessStatus.NOT_A_RHYME:
            self._set_event(state, "player", ["Not a rhyme"], "bad")
        elif res.status == game.GuessStatus.VALID_ENGLISH_MISSING_CMU:
            self._track_rhyme_attempt(state.prompt, guess)
            self._set_event(state, "player", ["Not in rhyming dictionary"], "bad")
        elif res.status == game.GuessStatus.NOT_RECOGNIZED_ENGLISH:
            self._set_event(state, "player", ["Not a valid word"], "bad")
        elif res.status == game.GuessStatus.NOT_PLAUSIBLE_TOKEN:
            self._set_event(state, "player", ["Not a valid word"], "bad")
        elif res.status == game.GuessStatus.SAME_AS_PROMPT:
            self._set_event(state, "player", ["Need a different word"], "bad")
        else:
            self._set_event(state, "player", ["Try again"], "bad")

    def handle_bot_commit(self) -> None:
        state = self.state
        if not self._is_active_bot(state, state.turn) or not state.pending_bot_word:
            return

        if state.pending_bot_correct:
            bonus = game.syllable_match_bonus(state.prompt, state.pending_bot_word)
            if bonus:
                self._award_points(state, state.pending_bot_actor, bonus)
            state.used_words.add(state.pending_bot_word.lower())
            state.used_keys.add(self._word_key(state.pending_bot_word))
            state.round_turns += 1
            if bonus:
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
            winner = self._next_turn(state.turn)
            self._award_points(state, winner, state.round_turns)
            self._set_event(state, winner, [f"Round over. +{state.round_turns} points"], "good")
            self._start_round(state, winner)
            return

        if self._is_active_bot(state, state.turn) and state.bot_action_mono is not None and now >= state.bot_action_mono:
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
                winner = self._next_turn(state.turn)
                self._award_points(state, winner, state.round_turns)
                self._set_event(state, winner, [f"Round over. +{state.round_turns} points"], "good")
                self._start_round(state, winner)
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
        if self._is_active_bot(state, turn):
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
        state.round_turns = 0
        state.last_player_word = ""
        state.last_bot_word = ""
        state.pending_bot_word = ""
        state.pending_bot_correct = False
        state.pending_bot_actor = ""
        state.last_bot_actor = ""
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
        if actor == "player":
            state.player_score += points
        elif actor == "bot1":
            state.bot1_score += points
        elif actor == "bot2":
            state.bot2_score += points
        elif actor == "bot3":
            state.bot3_score += points
        elif actor == "bot4":
            state.bot4_score += points

    def _next_turn(self, turn: str) -> str:
        active = self._active_turns(self.state)
        try:
            idx = active.index(turn)
        except ValueError:
            return "player"
        return active[(idx + 1) % len(active)]

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
        return ["player"] + [f"bot{i}" for i in range(1, state.bot_count + 1)]

    def _is_active_bot(self, state: GameState, turn: str) -> bool:
        return turn in self._active_turns(state) and turn != "player"

    def _normalize_bot_count(self, value: int | str) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 1
        return max(1, min(4, count))

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
