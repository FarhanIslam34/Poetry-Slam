from __future__ import annotations
import random 
import pronouncing 
from prompt_dictionary import load_or_create_prompts, MIN_RHYMES, MAX_RHYMES

def get_pron(word: str):
    """Return first pronunciation for a word, or None if OOV."""
    prons = pronouncing.phones_for_word(word.lower())
    return prons[0] if prons else None 

def words_rhyme(w1: str, w2: str) -> bool:
    """Strict rhyme check: identical rhyming_part in CMUdict."""
    p1 = get_pron(w1)
    p2 = get_pron(w2)
    if not p1 or not p2:
        return False
    return pronouncing.rhyming_part(p1) == pronouncing.rhyming_part(p2) 

def is_valid_word(word: str) -> bool:
    """Valid if present in CMUdict."""
    return bool(pronouncing.phones_for_word(word.lower()))

PROMPTS = load_or_create_prompts()

def pick_prompt() -> str:
    return random.choice(PROMPTS)

def play_round() -> bool:
    prompt = pick_prompt()
    print(f'Enter a word that rhymes with "{prompt.capitalize()}" (or "quit" to exit):')
    guess = input("> ").strip()
    if guess.lower() in ("quit", "exit"):
        print("Goodbye!")
        return False
    if not is_valid_word(guess):
        print(f'"{guess}" is not recognized as a valid English word.')
        return True
    if guess.lower() == prompt.lower():
        print("Nice try, but you need a *different* word that rhymes.")
        return True
    if words_rhyme(prompt, guess):
        print("Correct!")
        return True
    else:
        print(f'"{guess}" does not rhyme with "{prompt}", play again?')
        return True
    
def main():
    print("Rhyme Game – type a rhyming word!")
    print("---------------------------------")
    while True:
        if not play_round():
            break

if __name__ == "__main__":
        main() 
