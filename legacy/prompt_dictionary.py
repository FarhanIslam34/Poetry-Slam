# prompt_dictionary.py
from __future__ import annotations
import json
from pathlib import Path
from typing import List
import pronouncing 
import cmudict

# Configuration for what counts as a good prompt
MIN_RHYMES = 100
MAX_RHYMES = 600
# Where to store the JSON file of prompts 
BASE_DIR = Path(__file__).parent 
PROMPT_DIR = BASE_DIR / "prompt_dictionaries"
PROMPT_DIR.mkdir(parents=True, exist_ok=True) 
PROMPT_FILE = PROMPT_DIR / f"rhyme_prompts_{MIN_RHYMES}_{MAX_RHYMES}.json" 

cmu = cmudict.dict()

def all_words():
    return [w for w in cmu.keys() if "(" not in w]

def build_prompts(min_rhymes,max_rhymes) -> List[str]: 
    # Build the list of prompts: 
    prompts: list[str] = []     
    words = all_words()
    for w in words:         
        if "(" in w:
            continue
        rhymes = pronouncing.rhymes(w)
        n = len(rhymes)
        if min_rhymes <= n <= max_rhymes:
            prompts.append(w)
            print(w+" Added")
    return prompts

def load_or_create_prompts() -> list[str]:
    """
    Load prompts from JSON if it exists and is valid;
    otherwise build prompts and write them to JSON.
    """
    if PROMPT_FILE.exists():
        try:
            with PROMPT_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and all(isinstance(x, str) for x in data):
                    return data
        except Exception:
            # Corrupted JSON -> fall through to rebuild
            pass

    prompts = build_prompts(MIN_RHYMES, MAX_RHYMES)
    if not prompts:
        raise RuntimeError(
                f"No prompts found with {MIN_RHYMES}–{MAX_RHYMES} rhymes. "
                "Try adjusting MIN_RHYMES / MAX_RHYMES."
                )
    with PROMPT_FILE.open("w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
        
    return prompts 
