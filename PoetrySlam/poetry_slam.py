# poetry_slam.py
from __future__ import annotations

import functools
import json
import random
import re
import textwrap
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import pronouncing
from wordfreq import zipf_frequency

from prompt_dictionary import load_or_create_prompts


# ----------------------------
# Normalization / token checks
# ----------------------------

_WORD_RE = re.compile(r"^[A-Za-z]+(?:[\'-][A-Za-z]+)*$")
_VOWEL_RE = re.compile(r"[0-2]$")

_DATA_DIR = Path(__file__).parent / "data"
_CUSTOM_RHYME_PATH = _DATA_DIR / "custom_rhymes.json"


def normalize(word: str) -> str:
    return (word or "").strip().lower()


def is_plausible_word_token(word: str) -> bool:
    w = normalize(word)
    return bool(w) and bool(_WORD_RE.match(w))


def is_recognized_english_word(word: str) -> bool:
    """
    Uses wordfreq to decide whether this looks like a real English word token.
    (Assumes wordfreq is installed.)
    """
    w = normalize(word)
    if not is_plausible_word_token(w):
        return False

    if "-" in w:
        parts = [p for p in w.split("-") if p]
        return bool(parts) and all(zipf_frequency(p, "en") > 0.0 for p in parts)

    if zipf_frequency(w, "en") > 0.0:
        return True
    if "'" in w and zipf_frequency(w.replace("'", ""), "en") > 0.0:
        return True

    return False


# ----------------------------
# Pronunciation / rhyme logic
# ----------------------------

def get_prons(word: str) -> list[str]:
    """All CMU pronunciations for the word (possibly empty)."""
    return pronouncing.phones_for_word(normalize(word))


def rhyme_parts(word: str) -> set[str]:
    """All CMU rhyming parts for the word across pronunciations (possibly empty)."""
    prons = get_prons(word)
    if prons:
        return {pronouncing.rhyming_part(p) for p in prons}
    return custom_rhyme_parts(word)


def _load_custom_rhymes() -> dict:
    if not _CUSTOM_RHYME_PATH.exists():
        return {"version": 1, "words": {}}
    try:
        payload = json.loads(_CUSTOM_RHYME_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "words": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "words": {}}
    if "words" not in payload or not isinstance(payload.get("words"), dict):
        return {"version": 1, "words": {}}
    return payload


def _save_custom_rhymes(payload: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CUSTOM_RHYME_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def custom_rhyme_parts(word: str) -> set[str]:
    payload = _load_custom_rhymes()
    entry = payload.get("words", {}).get(normalize(word), {})
    parts = entry.get("rhyming_parts", [])
    if not isinstance(parts, list):
        return set()
    return {p for p in parts if isinstance(p, str)}


def add_custom_rhyme(word: str, prompt: str) -> bool:
    parts = rhyme_parts(prompt)
    if not parts:
        return False
    payload = _load_custom_rhymes()
    words = payload.setdefault("words", {})
    key = normalize(word)
    entry = words.setdefault(key, {"rhyming_parts": [], "prompts": []})
    for part in sorted(parts):
        if part not in entry["rhyming_parts"]:
            entry["rhyming_parts"].append(part)
    if prompt not in entry["prompts"]:
        entry["prompts"].append(prompt)
    _save_custom_rhymes(payload)
    return True


def words_rhyme(w1: str, w2: str) -> bool:
    """
    Strict rhyme check:
    True iff there exists a shared CMU rhyming_part across any pronunciations.
    """
    r1, r2 = rhyme_parts(w1), rhyme_parts(w2)
    return bool(r1 and r2 and (r1 & r2))


def syllable_match_bonus(prompt: str, guess: str) -> int:
    """
    Returns bonus points based on how many syllables the prompt has
    beyond the rhyming part.
    Bonus equals (prompt syllables - rhyming part syllables).
    """
    best = 0
    for p1 in get_prons(prompt):
        for p2 in get_prons(guess):
            rp1 = pronouncing.rhyming_part(p1)
            rp2 = pronouncing.rhyming_part(p2)
            if rp1 != rp2:
                continue
            syllables1 = sum(1 for ph in p1.split() if _VOWEL_RE.search(ph))
            syllables2 = sum(1 for ph in p2.split() if _VOWEL_RE.search(ph))
            if syllables2 < syllables1:
                continue
            rhyming_syllables = sum(1 for ph in rp1.split() if _VOWEL_RE.search(ph))
            best = max(best, max(0, syllables1 - rhyming_syllables))
    return best


# ----------------------------
# Slant rhyme settings (toggleable)
# ----------------------------

@dataclass(frozen=True)
class RhymeSettings:
    """
    Settings are designed as *expanding* acceptance classes:
      - Strict rhyme is always accepted.
      - Each enabled toggle can only add more accepted answers.
    """
    # Accept if the guess matches the prompt rhyme tail plus one extra final consonant
    # (e.g., "bed" -> "beds", "beat" -> "beats").
    allow_trailing_consonant_cluster: bool = False

    # Accept if the final consonant differs but is "close" by phonetic class.
    allow_final_consonant_class_substitution: bool = False

    # Subtoggles for final consonant substitution:
    # - ignore_voicing: keep place+manner same; allow voiced/voiceless swap (t↔d, s↔z, p↔b, k↔g)
    # - same_manner: allow any consonants with the same manner (stop↔stop, fricative↔fricative, ...)
    # - same_place: allow any consonants with the same place (alveolar↔alveolar, velar↔velar, ...)
    coda_ignore_voicing: bool = False
    coda_same_manner: bool = False
    coda_same_place: bool = False

    # Accept if the stressed vowel matches, ignoring the coda entirely (assonant end match).
    allow_vowel_match_only: bool = False

    # Expand what counts as a "matching vowel" for all vowel-based checks above.
    allow_near_vowel_substitution: bool = False

    # Subtoggles for near-vowel substitution.
    near_vowel_tense_lax_pairs: bool = False
    near_vowel_short_front_bucket: bool = False


# CMUdict uses ARPAbet phones. For the toggles above, we only need coarse features.
# This is intentionally small and conservative: unknown phones simply don't match by class.
_CONSONANT_FEATURES: dict[str, tuple[str, str, str]] = {
    # phone: (place, manner, voicing)
    "P": ("bilabial", "stop", "voiceless"),
    "B": ("bilabial", "stop", "voiced"),
    "T": ("alveolar", "stop", "voiceless"),
    "D": ("alveolar", "stop", "voiced"),
    "K": ("velar", "stop", "voiceless"),
    "G": ("velar", "stop", "voiced"),
    "CH": ("postalveolar", "affricate", "voiceless"),
    "JH": ("postalveolar", "affricate", "voiced"),
    "F": ("labiodental", "fricative", "voiceless"),
    "V": ("labiodental", "fricative", "voiced"),
    "TH": ("dental", "fricative", "voiceless"),
    "DH": ("dental", "fricative", "voiced"),
    "S": ("alveolar", "fricative", "voiceless"),
    "Z": ("alveolar", "fricative", "voiced"),
    "SH": ("postalveolar", "fricative", "voiceless"),
    "ZH": ("postalveolar", "fricative", "voiced"),
    "HH": ("glottal", "fricative", "voiceless"),
    "M": ("bilabial", "nasal", "voiced"),
    "N": ("alveolar", "nasal", "voiced"),
    "NG": ("velar", "nasal", "voiced"),
    "L": ("alveolar", "liquid", "voiced"),
    "R": ("alveolar", "liquid", "voiced"),
    "Y": ("palatal", "glide", "voiced"),
    "W": ("labiovelar", "glide", "voiced"),
}

# Near-vowel groups are also ARPAbet (stress stripped).
# These are typical "game-friendly" groupings; they intentionally do not try to model accent variation.
_TENSE_LAX_PAIRS: dict[str, str] = {
    "IY": "IH", "IH": "IY",
    "EY": "EH", "EH": "EY",
    "UW": "UH", "UH": "UW",
    "OW": "AO", "AO": "OW",  # coarse; optional but useful
    "AA": "AH", "AH": "AA",  # coarse; optional but useful
}
_SHORT_FRONT_BUCKET: set[str] = {"IH", "EH", "AE"}


def _strip_stress(phone: str) -> str:
    return _VOWEL_RE.sub("", phone)


def _is_vowel(phone: str) -> bool:
    return bool(_VOWEL_RE.search(phone))


def _is_consonant(phone: str) -> bool:
    # ARPAbet consonants have no stress digit, so this is a safe heuristic here.
    return bool(phone) and not _is_vowel(phone)


def _vowels_equivalent(v1: str, v2: str, s: RhymeSettings) -> bool:
    if v1 == v2:
        return True
    if not s.allow_near_vowel_substitution:
        return False

    # Subtoggle: tense↔lax pairs (e.g., IY↔IH)
    if s.near_vowel_tense_lax_pairs and _TENSE_LAX_PAIRS.get(v1) == v2:
        return True

    # Subtoggle: short-front bucket (IH/EH/AE treated as "near")
    if s.near_vowel_short_front_bucket and (v1 in _SHORT_FRONT_BUCKET) and (v2 in _SHORT_FRONT_BUCKET):
        return True

    return False


def _consonants_compatible(c1: str, c2: str, s: RhymeSettings) -> bool:
    if c1 == c2:
        return True
    f1 = _CONSONANT_FEATURES.get(c1)
    f2 = _CONSONANT_FEATURES.get(c2)
    if not f1 or not f2:
        return False

    place1, manner1, voice1 = f1
    place2, manner2, voice2 = f2

    # If no subtoggles are enabled, do not allow substitution (conservative default).
    if not (s.coda_ignore_voicing or s.coda_same_manner or s.coda_same_place):
        return False

    if s.coda_ignore_voicing and (place1 == place2) and (manner1 == manner2) and (voice1 != voice2):
        return True
    if s.coda_same_manner and (manner1 == manner2):
        return True
    if s.coda_same_place and (place1 == place2):
        return True

    return False


def _pron_info(word: str) -> list[dict[str, object]]:
    """
    Extract a comparable "ending signature" per pronunciation:
      - vowel: last vowel phone (stress stripped)
      - tail: phones after that vowel (stress preserved on vowels, but tails are typically consonants)
      - syllables: count of vowel phones in the full pronunciation
    """
    infos: list[dict[str, object]] = []
    for phones in get_prons(word):
        parts = phones.split()
        vowel_idx = None
        syllables = 0
        for i, p in enumerate(parts):
            if _VOWEL_RE.search(p):
                syllables += 1
                vowel_idx = i
        if vowel_idx is None:
            continue
        vowel = _strip_stress(parts[vowel_idx])
        tail = tuple(parts[vowel_idx + 1 :])
        infos.append({"vowel": vowel, "tail": tail, "syllables": syllables})
    return infos


def _is_one_extra_final_consonant(t1: tuple[str, ...], t2: tuple[str, ...]) -> bool:
    """
    True iff one tail is exactly the other tail plus one extra *final consonant*.
    This powers the "Allow trailing consonant cluster" toggle.
    """
    if len(t1) + 1 == len(t2):
        extra = t2[-1]
        return t2[:-1] == t1 and _is_consonant(extra)
    if len(t2) + 1 == len(t1):
        extra = t1[-1]
        return t1[:-1] == t2 and _is_consonant(extra)
    return False


def _final_consonant_class_substitution(t1: tuple[str, ...], t2: tuple[str, ...], s: RhymeSettings) -> bool:
    """
    True iff tails are identical except the final consonant, which is allowed to vary
    by phonetic-class subtoggles (voicing / manner / place).
    """
    if len(t1) != len(t2) or len(t1) == 0:
        return False
    if t1[:-1] != t2[:-1]:
        return False
    c1, c2 = t1[-1], t2[-1]
    if not (_is_consonant(c1) and _is_consonant(c2)):
        return False
    c1, c2 = _strip_stress(c1), _strip_stress(c2)
    return _consonants_compatible(c1, c2, s)


def words_rhyme_with_settings(prompt: str, guess: str, settings: RhymeSettings) -> bool:
    """
    Expanding acceptance model.

    Order matters: earlier checks are "closer" to perfect rhyme, later checks are broader.
    """
    # 1) Perfect rhyme always wins.
    if words_rhyme(prompt, guess):
        return True

    infos1 = _pron_info(prompt)
    infos2 = _pron_info(guess)
    if not infos1 or not infos2:
        return False

    for i1 in infos1:
        for i2 in infos2:
            if i1["syllables"] != i2["syllables"]:
                continue
            v1 = i1["vowel"]
            v2 = i2["vowel"]
            t1 = i1["tail"]
            t2 = i2["tail"]

            # 2) Allow trailing consonant cluster (one extra final consonant).
            if settings.allow_trailing_consonant_cluster and _vowels_equivalent(v1, v2, settings):
                if _is_one_extra_final_consonant(t1, t2):
                    return True

            # 3) Allow final consonant class substitution (keep vowel + tail shape; vary final consonant by class).
            if settings.allow_final_consonant_class_substitution and _vowels_equivalent(v1, v2, settings):
                if _final_consonant_class_substitution(t1, t2, settings):
                    return True

            # 4) Allow vowel match only (assonant end match): vowel matches, ignore tail.
            if settings.allow_vowel_match_only and _vowels_equivalent(v1, v2, settings):
                return True

    return False


# ----------------------------
# Accepted answers (cached)
# ----------------------------

@functools.lru_cache(maxsize=512)
def accepted_by_rhyme_part(prompt: str) -> dict[str, list[str]]:
    """
    Acceptable answers grouped by each rhyming part of the prompt.
    Keys are rhyming_part strings; values are sorted lowercase words.
    """
    p = normalize(prompt)
    groups: dict[str, list[str]] = {}

    for rp in sorted(rhyme_parts(p)):
        pattern = re.escape(rp) + r"$"
        words = pronouncing.search(pattern)
        cleaned = sorted({w.lower() for w in words if w.lower() != p}, key=str.lower)
        groups[rp] = cleaned

    return groups


@functools.lru_cache(maxsize=512)
def accepted_words(prompt: str) -> list[str]:
    """Union of all acceptable answers across pronunciation families (sorted)."""
    all_words: set[str] = set()
    for answers in accepted_by_rhyme_part(prompt).values():
        all_words.update(a.lower() for a in answers)
    all_words.discard(normalize(prompt))
    return sorted(all_words, key=str.lower)


def sample_accepted_words(prompt: str, k: int = 100) -> list[str]:
    """
    Random sample (up to k) of acceptable answers, returned sorted for display.
    """
    words = accepted_words(prompt)
    if not words:
        return []
    k = min(k, len(words))
    sample = random.sample(words, k=k)
    sample.sort(key=str.lower)
    return sample


# ----------------------------
# Guess judging (UI-agnostic)
# ----------------------------

class GuessStatus(Enum):
    EMPTY = auto()
    QUIT_COMMAND = auto()
    NOT_PLAUSIBLE_TOKEN = auto()
    VALID_ENGLISH_MISSING_CMU = auto()
    NOT_RECOGNIZED_ENGLISH = auto()
    SAME_AS_PROMPT = auto()
    NOT_A_RHYME = auto()
    CORRECT = auto()


@dataclass(frozen=True)
class GuessResult:
    status: GuessStatus
    message: str
    show_accepteds: bool = False
    next_prompt: str | None = None


PROMPTS = load_or_create_prompts()


def pick_prompt() -> str:
    return random.choice(PROMPTS)


def judge_guess(prompt: str, guess: str, *, settings: RhymeSettings | None = None) -> GuessResult:
    """
    Pure decision logic: no printing, no UI assumptions.

    If `settings` is provided, we accept:
      - strict rhymes, OR
      - any slant-rhyme rule enabled by settings (see RhymeSettings for details).
    """
    p = normalize(prompt)
    raw = (guess or "").strip()
    g = raw.lower()

    if not raw:
        return GuessResult(GuessStatus.EMPTY, "Please enter a word.")

    if g in ("quit", "exit"):
        return GuessResult(GuessStatus.QUIT_COMMAND, "Quit command received.")

    if not is_plausible_word_token(raw):
        return GuessResult(
            GuessStatus.NOT_PLAUSIBLE_TOKEN,
            f'"{raw}" is not recognized as a valid English word.',
            show_accepteds=True,
        )

    if not get_prons(raw):
        if is_recognized_english_word(raw):
            if words_rhyme(p, raw):
                return GuessResult(
                    GuessStatus.CORRECT,
                    "Correct!",
                    show_accepteds=False,
                    next_prompt=pick_prompt(),
                )
            return GuessResult(
                GuessStatus.VALID_ENGLISH_MISSING_CMU,
                f'"{raw}" is a valid English word, but does not have an entry in the CMU dictionary.',
                show_accepteds=True,
            )
        return GuessResult(
            GuessStatus.NOT_RECOGNIZED_ENGLISH,
            f'"{raw}" is not recognized as a valid English word.',
            show_accepteds=True,
        )

    if g == p:
        return GuessResult(
            GuessStatus.SAME_AS_PROMPT,
            "Nice try, but you need a *different* word that rhymes.",
            show_accepteds=True,
        )

    # Strict rhyme or settings-based slant rhyme.
    is_ok = words_rhyme(p, raw) or (
        settings is not None and words_rhyme_with_settings(p, raw, settings)
    )
    if not is_ok:
        return GuessResult(
            GuessStatus.NOT_A_RHYME,
            f'"{raw}" does not rhyme with "{prompt}".',
            show_accepteds=True,
        )

    return GuessResult(
        GuessStatus.CORRECT,
        "Correct!",
        show_accepteds=False,
        next_prompt=pick_prompt(),
    )


# ----------------------------
# CLI (presentation layer)
# ----------------------------

def print_possible_answers(prompt: str) -> None:
    groups = accepted_by_rhyme_part(prompt)

    if not groups:
        print(f'No rhymes found in the dictionary for "{prompt}".')
        return

    if len(groups) == 1:
        (_, answers), = groups.items()
        print(f"Possible answers ({len(answers)}):")
        print(textwrap.fill(", ".join(answers), width=88) if answers else "(none)")
        return

    print(f'Possible answers by pronunciation family for "{prompt}":')
    for i, (rp, answers) in enumerate(groups.items(), start=1):
        print(f"\nFamily {i} (rhyming part: {rp}) — {len(answers)} answer(s):")
        print(textwrap.fill(", ".join(answers), width=88) if answers else "(none)")


def play_round() -> bool:
    prompt = pick_prompt()
    print(f'Enter a word that rhymes with "{prompt.capitalize()}" (or "quit" to exit):')
    guess = input("> ")

    # CLI uses strict rhyme by default.
    res = judge_guess(prompt, guess)

    if res.status == GuessStatus.QUIT_COMMAND:
        print("Goodbye!")
        return False

    print(res.message)
    if res.show_accepteds:
        print_possible_answers(prompt)

    # Correct advances implicitly by starting a new round in the loop.
    return True


def main() -> None:
    print("Rhyme Game – type a rhyming word!")
    print("---------------------------------")
    while play_round():
        pass


if __name__ == "__main__":
    main()
