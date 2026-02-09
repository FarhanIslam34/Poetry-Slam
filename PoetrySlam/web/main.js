import {
  fetchState,
  startNewGame,
  submitGuess,
  commitBot,
  togglePause,
  updateConfig,
  fetchRhymeAttempts,
  confirmRhyme,
  listRooms,
  createRoom,
  joinRoom,
} from "./api.js";
import { createRenderer } from "./render.js";

const guessEl = document.getElementById("guess");
const newGameBtn = document.getElementById("new-game");
const pauseBtn = document.getElementById("pause-game");
const difficultyEl = document.getElementById("difficulty");
const botCountEl = document.getElementById("bot-count");
const evaluateBtn = document.getElementById("evaluate-rhymes");
const currentRoomEl = document.getElementById("current-room");
const roomsListEl = document.getElementById("rooms-list");
const createRoomBtn = document.getElementById("create-room");
const joinRoomBtn = document.getElementById("join-room");
const joinRoomInput = document.getElementById("join-room-id");
const rhymeModal = document.getElementById("rhyme-modal");
const rhymeCloseBtn = document.getElementById("close-rhyme-modal");
const rhymeListEl = document.getElementById("rhyme-attempts");
const rhymeEmptyEl = document.getElementById("rhyme-empty");
const allowTrailingConsonantClusterEl = document.getElementById(
  "allow-trailing-consonant-cluster"
);
const allowFinalConsonantClassSubstitutionEl = document.getElementById(
  "allow-final-consonant-class-substitution"
);
const codaIgnoreVoicingEl = document.getElementById("coda-ignore-voicing");
const codaSameMannerEl = document.getElementById("coda-same-manner");
const codaSamePlaceEl = document.getElementById("coda-same-place");
const allowVowelMatchOnlyEl = document.getElementById("allow-vowel-match-only");
const allowNearVowelSubstitutionEl = document.getElementById(
  "allow-near-vowel-substitution"
);
const nearVowelTenseLaxPairsEl = document.getElementById(
  "near-vowel-tense-lax-pairs"
);
const nearVowelShortFrontBucketEl = document.getElementById(
  "near-vowel-short-front-bucket"
);
const slantBonusEl = document.getElementById("slant-bonus");

const settingEls = [
  allowTrailingConsonantClusterEl,
  allowFinalConsonantClassSubstitutionEl,
  codaIgnoreVoicingEl,
  codaSameMannerEl,
  codaSamePlaceEl,
  allowVowelMatchOnlyEl,
  allowNearVowelSubstitutionEl,
  nearVowelTenseLaxPairsEl,
  nearVowelShortFrontBucketEl,
  slantBonusEl,
];

const slantSettingEls = [
  allowTrailingConsonantClusterEl,
  allowFinalConsonantClassSubstitutionEl,
  codaIgnoreVoicingEl,
  codaSameMannerEl,
  codaSamePlaceEl,
  allowVowelMatchOnlyEl,
  allowNearVowelSubstitutionEl,
  nearVowelTenseLaxPairsEl,
  nearVowelShortFrontBucketEl,
];

const toggleGroups = [
  {
    parent: allowFinalConsonantClassSubstitutionEl,
    children: [codaIgnoreVoicingEl, codaSameMannerEl, codaSamePlaceEl],
  },
  {
    parent: allowNearVowelSubstitutionEl,
    children: [nearVowelTenseLaxPairsEl, nearVowelShortFrontBucketEl],
  },
];

const playersRowEl = document.getElementById("players-row");

const elements = {
  guessEl,
  botCountEl,
  playersRowEl,
  timerEl: document.getElementById("timer"),
  remainingEl: document.getElementById("remaining"),
  rhymePartEl: document.getElementById("rhyme-part"),
  promptStackEl: document.getElementById("prompt-stack"),
  pauseBtn,
  settingEls,
  evaluateBtn,
};

let roomId = localStorage.getItem("room_id") || "";
let playerId = localStorage.getItem("player_id") || "";
const makeClientId = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `cid-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};
const clientId = localStorage.getItem("client_id") || makeClientId();
localStorage.setItem("client_id", clientId);

function setRoom(id, pid) {
  roomId = id || "";
  playerId = pid || "";
  localStorage.setItem("room_id", roomId);
  localStorage.setItem("player_id", playerId);
  if (currentRoomEl) {
    currentRoomEl.textContent = roomId || "—";
  }
}

const renderer = createRenderer({
  elements,
  onBotCommit: () => commitBot({ roomId }),
  onAutoSubmit: () => submitGuessAction(),
});

function updateToggleGroup(group) {
  const { parent, children } = group;
  if (!parent) {
    return;
  }
  const checks = children.map((child) => child?.checked);
  const anyChecked = checks.some(Boolean);
  const allChecked = checks.length > 0 && checks.every(Boolean);
  parent.checked = allChecked;
  parent.indeterminate = anyChecked && !allChecked;
}

function setChildrenChecked(group, checked) {
  group.children.forEach((child) => {
    if (child) {
      child.checked = checked;
    }
  });
  updateToggleGroup(group);
}

function updateSlantBonusAvailability() {
  if (!slantBonusEl) {
    return;
  }
  const anySlant = slantSettingEls.some((el) => el && el.checked);
  slantBonusEl.disabled = !anySlant;
  if (!anySlant) {
    slantBonusEl.checked = false;
  }
}

toggleGroups.forEach((group) => {
  if (group.parent) {
    group.parent.addEventListener("change", () => {
      setChildrenChecked(group, group.parent.checked);
      updateSlantBonusAvailability();
    });
  }
  group.children.forEach((child) => {
    if (child) {
      child.addEventListener("change", () => {
        updateToggleGroup(group);
        updateSlantBonusAvailability();
      });
    }
  });
  updateToggleGroup(group);
});
slantSettingEls.forEach((el) => {
  if (el) {
    el.addEventListener("change", updateSlantBonusAvailability);
  }
});
updateSlantBonusAvailability();

async function submitGuessAction() {
  const guess = guessEl.value.trim();
  const difficulty = difficultyEl.value;
  const state = await submitGuess({
    guess,
    difficulty,
    roomId,
    clientId,
    allowTrailingConsonantCluster: !!allowTrailingConsonantClusterEl?.checked,
    allowFinalConsonantClassSubstitution: !!allowFinalConsonantClassSubstitutionEl?.checked,
    codaIgnoreVoicing: !!codaIgnoreVoicingEl?.checked,
    codaSameManner: !!codaSameMannerEl?.checked,
    codaSamePlace: !!codaSamePlaceEl?.checked,
    allowVowelMatchOnly: !!allowVowelMatchOnlyEl?.checked,
    allowNearVowelSubstitution: !!allowNearVowelSubstitutionEl?.checked,
    nearVowelTenseLaxPairs: !!nearVowelTenseLaxPairsEl?.checked,
    nearVowelShortFrontBucket: !!nearVowelShortFrontBucketEl?.checked,
    slantBonus: !!slantBonusEl?.checked,
  });
  renderer.renderState(state);
  guessEl.value = "";
  renderer.updateInputState();
  if (state.self_id && state.turn === state.self_id) {
    guessEl.focus();
  }
}

async function startGame() {
  const botCount = botCountEl ? Number.parseInt(botCountEl.value, 10) : undefined;
  const state = await startNewGame({ botCount, roomId, clientId });
  renderer.renderState(state);
  guessEl.value = "";
  guessEl.focus();
}

newGameBtn.addEventListener("click", () => {
  startGame().catch(console.error);
});

pauseBtn.addEventListener("click", () => {
  togglePause({ roomId, clientId })
    .then(renderer.renderState)
    .catch(console.error);
});

function renderRhymeAttempts(attempts) {
  rhymeListEl.replaceChildren();
  const hasAttempts = Array.isArray(attempts) && attempts.length > 0;
  rhymeEmptyEl.style.display = hasAttempts ? "none" : "block";
  if (!hasAttempts) {
    return;
  }
  attempts.forEach((attempt) => {
    const card = document.createElement("div");
    card.className = "attempt-card";
    const line = document.createElement("div");
    line.className = "attempt-line";
    line.innerHTML = `Prompt: <span>${attempt.prompt}</span> — Guess: <span>${attempt.guess}</span>`;
    const actions = document.createElement("div");
    actions.className = "attempt-actions";
    const yesBtn = document.createElement("button");
    yesBtn.className = "yes";
    yesBtn.textContent = "Yes, they rhyme";
    const noBtn = document.createElement("button");
    noBtn.textContent = "No";
    yesBtn.addEventListener("click", () => {
      confirmRhyme({
        prompt: attempt.prompt,
        guess: attempt.guess,
        accepted: true,
        roomId,
      })
        .then((payload) => renderRhymeAttempts(payload.attempts))
        .catch(console.error);
    });
    noBtn.addEventListener("click", () => {
      confirmRhyme({
        prompt: attempt.prompt,
        guess: attempt.guess,
        accepted: false,
        roomId,
      })
        .then((payload) => renderRhymeAttempts(payload.attempts))
        .catch(console.error);
    });
    actions.append(yesBtn, noBtn);
    card.append(line, actions);
    rhymeListEl.appendChild(card);
  });
}

function openRhymeModal() {
  fetchRhymeAttempts({ roomId })
    .then((payload) => {
      renderRhymeAttempts(payload.attempts);
      rhymeModal.classList.add("is-open");
      rhymeModal.setAttribute("aria-hidden", "false");
    })
    .catch(console.error);
}

function closeRhymeModal() {
  rhymeModal.classList.remove("is-open");
  rhymeModal.setAttribute("aria-hidden", "true");
}

if (evaluateBtn) {
  evaluateBtn.addEventListener("click", () => {
    openRhymeModal();
  });
}

if (rhymeCloseBtn) {
  rhymeCloseBtn.addEventListener("click", () => {
    closeRhymeModal();
  });
}

if (rhymeModal) {
  rhymeModal.addEventListener("click", (event) => {
    if (event.target === rhymeModal) {
      closeRhymeModal();
    }
  });
}

if (botCountEl) {
  botCountEl.addEventListener("change", () => {
    const value = Number.parseInt(botCountEl.value, 10);
    updateConfig({ botCount: value, roomId, clientId })
      .then(renderer.renderState)
      .catch(console.error);
  });
}

guessEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    submitGuessAction().catch(console.error);
  }
});

guessEl.addEventListener("input", () => {
  renderer.updateInputState();
});

if (roomId) {
  fetchState({ difficulty: difficultyEl.value, roomId, clientId })
    .then(renderer.renderState)
    .catch(() => {
      startGame().catch(console.error);
    });
}

function pollState() {
  if (!roomId) {
    return;
  }
  fetchState({ difficulty: difficultyEl.value, roomId, clientId })
    .then(renderer.renderState)
    .catch(console.error);
}

setInterval(pollState, 250);

function renderRooms(rooms) {
  if (!roomsListEl) {
    return;
  }
  roomsListEl.replaceChildren();
  (rooms || []).forEach((room) => {
    const row = document.createElement("div");
    row.className = "room-card";
    const label = document.createElement("div");
    label.textContent = `${room.room_id} · ${room.players}/${room.capacity}`;
    const join = document.createElement("button");
    join.className = "ghost";
    join.textContent = "Join";
    join.addEventListener("click", () => {
      joinRoom({ roomId: room.room_id, clientId })
        .then((payload) => {
          setRoom(payload.room_id, payload.player_id);
          renderer.renderState(payload.state);
        })
        .catch(console.error);
    });
    row.append(label, join);
    roomsListEl.appendChild(row);
  });
}

function refreshRooms() {
  listRooms()
    .then((payload) => renderRooms(payload.rooms))
    .catch(console.error);
}

if (createRoomBtn) {
  createRoomBtn.addEventListener("click", () => {
    const botCount = botCountEl ? Number.parseInt(botCountEl.value, 10) : 1;
    createRoom({ botCount, clientId })
      .then((payload) => {
        setRoom(payload.room_id, payload.player_id);
        renderer.renderState(payload.state);
        refreshRooms();
      })
      .catch(console.error);
  });
}

if (joinRoomBtn) {
  joinRoomBtn.addEventListener("click", () => {
    const value = (joinRoomInput?.value || "").trim();
    if (!value) {
      return;
    }
    joinRoom({ roomId: value, clientId })
      .then((payload) => {
        setRoom(payload.room_id, payload.player_id);
        renderer.renderState(payload.state);
        refreshRooms();
      })
      .catch(console.error);
  });
}

setRoom(roomId, playerId);
refreshRooms();
if (!roomId && createRoomBtn) {
  const botCount = botCountEl ? Number.parseInt(botCountEl.value, 10) : 1;
  createRoom({ botCount, clientId })
    .then((payload) => {
      setRoom(payload.room_id, payload.player_id);
      renderer.renderState(payload.state);
      refreshRooms();
    })
    .catch(console.error);
}
