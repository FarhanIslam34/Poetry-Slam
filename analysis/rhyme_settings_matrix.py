from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PoetrySlam"))

import poetry_slam as game


@dataclass(frozen=True)
class Case:
    prompt: str
    guess: str
    note: str


def rhyme_pass(prompt: str, guess: str, settings: game.RhymeSettings | None) -> str:
    if not game.get_prons(prompt) or not game.get_prons(guess):
        return "NO_PRON"
    if game.words_rhyme(prompt, guess):
        return "PASS"
    if settings and game.words_rhyme_with_settings(prompt, guess, settings):
        return "PASS"
    return "FAIL"


CONFIGS: list[tuple[str, game.RhymeSettings | None]] = [
    ("strict", None),
    ("trailing_consonant_cluster", game.RhymeSettings(allow_trailing_consonant_cluster=True)),
    (
        "final_consonant_voicing",
        game.RhymeSettings(
            allow_final_consonant_class_substitution=True,
            coda_ignore_voicing=True,
        ),
    ),
    (
        "final_consonant_same_manner",
        game.RhymeSettings(
            allow_final_consonant_class_substitution=True,
            coda_same_manner=True,
        ),
    ),
    (
        "final_consonant_same_place",
        game.RhymeSettings(
            allow_final_consonant_class_substitution=True,
            coda_same_place=True,
        ),
    ),
    ("vowel_match_only", game.RhymeSettings(allow_vowel_match_only=True)),
    (
        "near_vowel_tense_lax_vowel_only",
        game.RhymeSettings(
            allow_vowel_match_only=True,
            allow_near_vowel_substitution=True,
            near_vowel_tense_lax_pairs=True,
        ),
    ),
    (
        "near_vowel_short_front_vowel_only",
        game.RhymeSettings(
            allow_vowel_match_only=True,
            allow_near_vowel_substitution=True,
            near_vowel_short_front_bucket=True,
        ),
    ),
]


CASES: list[Case] = [
    Case("cat", "bat", "Strict rhyme baseline"),
    Case("light", "night", "Strict rhyme baseline"),
    Case("bed", "beds", "Trailing consonant cluster (+S)"),
    Case("fine", "find", "Trailing consonant cluster (+D)"),
    Case("bat", "bad", "Final consonant voicing (T/D)"),
    Case("cap", "cab", "Final consonant voicing (P/B)"),
    Case("back", "bag", "Final consonant voicing (K/G)"),
    Case("rate", "raise", "Final consonant same place (T/Z)"),
    Case("back", "bat", "Final consonant same manner (K/T)"),
    Case("sack", "sap", "Final consonant same manner (K/P)"),
    Case("late", "lame", "Vowel match only (ignore tail)"),
    Case("beam", "bean", "Vowel match only (ignore tail)"),
    Case("beat", "bit", "Near vowel tense/lax (IY/IH)"),
    Case("full", "fool", "Near vowel tense/lax (UH/UW)"),
    Case("pit", "pet", "Near vowel short-front bucket (IH/EH)"),
    Case("rick", "rack", "Near vowel short-front bucket (IH/AE)"),
]


def main() -> None:
    output_path = Path(__file__).resolve().with_suffix(".csv")
    headers = ["prompt", "guess", "note"] + [name for name, _ in CONFIGS]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for case in CASES:
            row = [case.prompt, case.guess, case.note]
            for _, settings in CONFIGS:
                row.append(rhyme_pass(case.prompt, case.guess, settings))
            writer.writerow(row)

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
