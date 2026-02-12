export async function fetchJSON(url, options = {}) {
  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    let detail = "";
    try {
      const payload = await resp.json();
      detail = payload?.error ? ` ${payload.error}` : "";
    } catch (err) {
      try {
        const text = await resp.text();
        detail = text ? ` ${text}` : "";
      } catch {
        detail = "";
      }
    }
    throw new Error(`Request failed: ${resp.status}.${detail}`);
  }
  return resp.json();
}

export function fetchState({ difficulty, roomId, clientId }) {
  const diff = encodeURIComponent(difficulty || "Medium");
  const room = encodeURIComponent(roomId || "");
  const client = encodeURIComponent(clientId || "");
  return fetchJSON(`/api/state?difficulty=${diff}&room_id=${room}&client_id=${client}`);
}

export function startNewGame({ botCount, roomId, clientId } = {}) {
  return fetchJSON("/api/new", {
    method: "POST",
    body: JSON.stringify({ bot_count: botCount, room_id: roomId, client_id: clientId }),
  });
}

export function submitGuess({
  guess,
  difficulty,
  roomId,
  clientId,
  allowTrailingConsonantCluster,
  allowFinalConsonantClassSubstitution,
  codaIgnoreVoicing,
  codaSameManner,
  codaSamePlace,
  allowVowelMatchOnly,
  allowNearVowelSubstitution,
  nearVowelTenseLaxPairs,
  nearVowelShortFrontBucket,
  slantBonus,
}) {
  return fetchJSON("/api/guess", {
    method: "POST",
    body: JSON.stringify({
      guess,
      difficulty,
      room_id: roomId,
      client_id: clientId,
      allow_trailing_consonant_cluster: allowTrailingConsonantCluster,
      allow_final_consonant_class_substitution: allowFinalConsonantClassSubstitution,
      coda_ignore_voicing: codaIgnoreVoicing,
      coda_same_manner: codaSameManner,
      coda_same_place: codaSamePlace,
      allow_vowel_match_only: allowVowelMatchOnly,
      allow_near_vowel_substitution: allowNearVowelSubstitution,
      near_vowel_tense_lax_pairs: nearVowelTenseLaxPairs,
      near_vowel_short_front_bucket: nearVowelShortFrontBucket,
      bonus_slant_rhyme: slantBonus,
    }),
  });
}

export function commitBot({ roomId }) {
  return fetchJSON("/api/bot_commit", {
    method: "POST",
    body: JSON.stringify({ room_id: roomId }),
  });
}

export function togglePause({ roomId, clientId }) {
  return fetchJSON("/api/pause", {
    method: "POST",
    body: JSON.stringify({ room_id: roomId, client_id: clientId }),
  });
}

export function updateConfig({ botCount, roomId, clientId }) {
  return fetchJSON("/api/config", {
    method: "POST",
    body: JSON.stringify({ bot_count: botCount, room_id: roomId, client_id: clientId }),
  });
}

export function fetchRhymeAttempts({ roomId }) {
  const room = encodeURIComponent(roomId || "");
  return fetchJSON(`/api/rhyme_attempts?room_id=${room}`);
}

export function confirmRhyme({ prompt, guess, accepted, roomId }) {
  return fetchJSON("/api/confirm_rhyme", {
    method: "POST",
    body: JSON.stringify({ prompt, guess, accepted, room_id: roomId }),
  });
}

export function listRooms() {
  return fetchJSON("/api/rooms");
}

export function createRoom({ botCount, clientId, name }) {
  return fetchJSON("/api/rooms/create", {
    method: "POST",
    body: JSON.stringify({ bot_count: botCount, client_id: clientId, name }),
  });
}

export function joinRoom({ roomId, clientId, name }) {
  return fetchJSON("/api/rooms/join", {
    method: "POST",
    body: JSON.stringify({ room_id: roomId, client_id: clientId, name }),
  });
}

export function testRhyme({ w1, w2 }) {
  const p1 = encodeURIComponent(w1 || "");
  const p2 = encodeURIComponent(w2 || "");
  return fetchJSON(`/api/test_rhyme?w1=${p1}&w2=${p2}`);
}

export function sendLiveInput({ roomId, clientId, text }) {
  return fetchJSON("/api/input", {
    method: "POST",
    body: JSON.stringify({ room_id: roomId, client_id: clientId, text }),
  });
}
