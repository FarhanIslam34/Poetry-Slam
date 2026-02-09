from __future__ import annotations

import random
from wordfreq import zipf_frequency

INVALID_BOT_WORDS = [
    "UHHHHHHHHH",
    "UMMMMMMMM",
]


def pick_bot_word(words: list[str], difficulty: str) -> tuple[str | None, bool]:
    if not words:
        return None, False

    accuracy = {
        "Easy": 0.5,
        "Medium": 0.8,
        "Hard": 1.0,
    }.get(difficulty, 0.8)

    if random.random() < 0.2:
        return random.choice(INVALID_BOT_WORDS), False

    risk = 0.2
    scores = [(w, zipf_frequency(w, "en")) for w in words]
    scores.sort(key=lambda x: x[1])

    if random.random() < risk:
        pool = [w for w, _ in scores[: max(3, len(scores) // 3)]]
    else:
        pool = words

    weights = [max(0.1, zipf_frequency(w, "en")) for w in pool]
    guess = random.choices(pool, weights=weights, k=1)[0]

    correct = random.random() <= accuracy
    return guess, correct
