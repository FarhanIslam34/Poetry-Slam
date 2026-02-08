from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import List

import cmudict
import pronouncing
from wordfreq import zipf_frequency  # pip install wordfreq


# Configuration for what counts as a good prompt
MIN_RHYMES = 5
MAX_RHYMES = 900

# Word familiarity threshold (higher = more common/easier)
# Typical tuning range:
#   4.0  -> fairly common
#   4.5  -> common spoken vocabulary (good default for a party game)
#   5.0  -> very common/easy
MIN_ZIPF = 3.5
MIN_PROMPT_LEN = 4

# Accept only simple word-like tokens; allow a single apostrophe for contractions
WORD_RE = re.compile(r"^[a-z]+(?:'[a-z]+)?$")

# Where to store the JSON file of prompts
BASE_DIR = Path(__file__).parent
PROMPT_DIR = BASE_DIR / "data" / "prompt_dictionaries"
PROMPT_DIR.mkdir(parents=True, exist_ok=True)
PROMPT_FILE = PROMPT_DIR / f"rhyme_prompts_{MIN_RHYMES}_{MAX_RHYMES}.json"

cmu = cmudict.dict()


def is_playable_token(w: str) -> bool:
    """
    Filter CMUdict headwords down to tokens that are likely playable in a word game.
    - Removes alternate pronunciation suffixes like WORD(1)
    - Rejects digits, hyphens, punctuation (except a single apostrophe for contractions)
    - Requires a minimum English frequency (Zipf scale)
    """
    if "(" in w:  # alternate pronunciations like WORD(1)
        return False
    if not WORD_RE.match(w):
        return False
    if zipf_frequency(w, "en") < MIN_ZIPF:
        return False
    return True


def all_words() -> list[str]:
    """Return filtered candidate words from CMUdict."""
    return [w.lower() for w in cmu.keys() if is_playable_token(w.lower())]


def rhyme_parts(word: str) -> set[str]:
    """Return all CMUdict rhyming_parts for a word (possibly empty)."""
    phones_list = pronouncing.phones_for_word(word)
    return {pronouncing.rhyming_part(p) for p in phones_list}


def build_rhyme_groups(words: list[str]) -> dict[str, set[str]]:
    """
    Group words by rhyming part across ALL pronunciations.
    A word can belong to multiple rhyme groups.
    """
    groups: dict[str, set[str]] = defaultdict(set)

    for w in words:
        for rp in rhyme_parts(w):
            groups[rp].add(w)

    return groups


def build_prompts(min_rhymes: int, max_rhymes: int) -> List[str]:
    """
    Build the list of prompt words whose rhyme-family size (across any pronunciation)
    is within the configured range.
    """
    prompts: list[str] = []
    words = all_words()
    rhyme_groups = build_rhyme_groups(words)

    for w in words:
        if len(w) < MIN_PROMPT_LEN:
            continue
        rps = rhyme_parts(w)
        if not rps:
            continue

        # Union all family members across all pronunciations, deduped.
        family: set[str] = set()
        for rp in rps:
            family |= rhyme_groups.get(rp, set())

        family.discard(w)
        playable_family = {rw for rw in family if is_playable_token(rw)}
        if not any(len(rw) > 1 for rw in playable_family):
            continue
        n = len(playable_family)

        if min_rhymes <= n <= max_rhymes:
            prompts.append(w)
            print(f"{w} Added")

    return prompts


def load_or_create_prompts() -> list[str]:
    """
    Load prompts from JSON if it exists and is valid; otherwise build and write prompts.
    """
    if PROMPT_FILE.exists():
        try:
            with PROMPT_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and all(isinstance(x, str) for x in data):
                    return data
        except Exception:
            pass  # fall through to rebuild

    prompts = build_prompts(MIN_RHYMES, MAX_RHYMES)
    if not prompts:
        raise RuntimeError(
            f"No prompts found with {MIN_RHYMES}–{MAX_RHYMES} rhymes. "
            "Try adjusting MIN_RHYMES / MAX_RHYMES (or MIN_ZIPF)."
        )

    with PROMPT_FILE.open("w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)

    return prompts
