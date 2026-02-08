export async function fetchJSON(url, options = {}) {
  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    throw new Error(`Request failed: ${resp.status}`);
  }
  return resp.json();
}

export function fetchState(difficulty) {
  const diff = encodeURIComponent(difficulty || "Medium");
  return fetchJSON(`/api/state?difficulty=${diff}`);
}

export function startNewGame({ botCount } = {}) {
  return fetchJSON("/api/new", {
    method: "POST",
    body: JSON.stringify({ bot_count: botCount }),
  });
}

export function submitGuess({
  guess,
  difficulty,
  allowTrailingConsonantCluster,
  allowFinalConsonantClassSubstitution,
  codaIgnoreVoicing,
  codaSameManner,
  codaSamePlace,
  allowVowelMatchOnly,
  allowNearVowelSubstitution,
  nearVowelTenseLaxPairs,
  nearVowelShortFrontBucket,
}) {
  return fetchJSON("/api/guess", {
    method: "POST",
    body: JSON.stringify({
      guess,
      difficulty,
      allow_trailing_consonant_cluster: allowTrailingConsonantCluster,
      allow_final_consonant_class_substitution: allowFinalConsonantClassSubstitution,
      coda_ignore_voicing: codaIgnoreVoicing,
      coda_same_manner: codaSameManner,
      coda_same_place: codaSamePlace,
      allow_vowel_match_only: allowVowelMatchOnly,
      allow_near_vowel_substitution: allowNearVowelSubstitution,
      near_vowel_tense_lax_pairs: nearVowelTenseLaxPairs,
      near_vowel_short_front_bucket: nearVowelShortFrontBucket,
    }),
  });
}

export function commitBot() {
  return fetchJSON("/api/bot_commit", { method: "POST", body: "{}" });
}

export function togglePause() {
  return fetchJSON("/api/pause", { method: "POST", body: "{}" });
}

export function updateConfig({ botCount }) {
  return fetchJSON("/api/config", {
    method: "POST",
    body: JSON.stringify({ bot_count: botCount }),
  });
}

export function fetchRhymeAttempts() {
  return fetchJSON("/api/rhyme_attempts");
}

export function confirmRhyme({ prompt, guess, accepted }) {
  return fetchJSON("/api/confirm_rhyme", {
    method: "POST",
    body: JSON.stringify({ prompt, guess, accepted }),
  });
}
