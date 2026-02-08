import {
  fetchState,
  startNewGame,
  submitGuess,
  commitBot,
  togglePause,
  updateConfig,
  fetchRhymeAttempts,
  confirmRhyme,
} from "./api.js";
import { createRenderer } from "./render.js";

const guessEl = document.getElementById("guess");
const newGameBtn = document.getElementById("new-game");
const pauseBtn = document.getElementById("pause-game");
const difficultyEl = document.getElementById("difficulty");
const botCountEl = document.getElementById("bot-count");
const evaluateBtn = document.getElementById("evaluate-rhymes");
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

const playerCard = document.getElementById("player-card");
const botIds = ["bot1", "bot2", "bot3", "bot4"];
const botCards = Object.fromEntries(
  botIds.map((id) => [id, document.getElementById(`${id}-card`)])
);

const elements = {
  guessEl,
  botCountEl,
  playerCard,
  botCards,
  playerScoreEl: playerCard.querySelector(".player-score"),
  botScoreEls: Object.fromEntries(
    botIds.map((id) => [id, botCards[id].querySelector(".player-score")])
  ),
  playerToast: document.getElementById("player-toast"),
  botToasts: {
    bot1: document.getElementById("bot-toast"),
    bot2: document.getElementById("bot2-toast"),
    bot3: document.getElementById("bot3-toast"),
    bot4: document.getElementById("bot4-toast"),
  },
  timerEl: document.getElementById("timer"),
  remainingEl: document.getElementById("remaining"),
  promptStackEl: document.getElementById("prompt-stack"),
  pauseBtn,
  settingEls,
  evaluateBtn,
};

const renderer = createRenderer({
  elements,
  botIds,
  onBotCommit: commitBot,
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

toggleGroups.forEach((group) => {
  if (group.parent) {
    group.parent.addEventListener("change", () => {
      setChildrenChecked(group, group.parent.checked);
    });
  }
  group.children.forEach((child) => {
    if (child) {
      child.addEventListener("change", () => updateToggleGroup(group));
    }
  });
  updateToggleGroup(group);
});

async function submitGuessAction() {
  const guess = guessEl.value.trim();
  const difficulty = difficultyEl.value;
  const state = await submitGuess({
    guess,
    difficulty,
    allowTrailingConsonantCluster: !!allowTrailingConsonantClusterEl?.checked,
    allowFinalConsonantClassSubstitution: !!allowFinalConsonantClassSubstitutionEl?.checked,
    codaIgnoreVoicing: !!codaIgnoreVoicingEl?.checked,
    codaSameManner: !!codaSameMannerEl?.checked,
    codaSamePlace: !!codaSamePlaceEl?.checked,
    allowVowelMatchOnly: !!allowVowelMatchOnlyEl?.checked,
    allowNearVowelSubstitution: !!allowNearVowelSubstitutionEl?.checked,
    nearVowelTenseLaxPairs: !!nearVowelTenseLaxPairsEl?.checked,
    nearVowelShortFrontBucket: !!nearVowelShortFrontBucketEl?.checked,
  });
  renderer.renderState(state);
  guessEl.value = "";
  renderer.updateInputState();
  if (state.turn === "player") {
    guessEl.focus();
  }
}

async function startGame() {
  const botCount = botCountEl ? Number.parseInt(botCountEl.value, 10) : undefined;
  const state = await startNewGame({ botCount });
  renderer.renderState(state);
  guessEl.value = "";
  guessEl.focus();
}

newGameBtn.addEventListener("click", () => {
  startGame().catch(console.error);
});

pauseBtn.addEventListener("click", () => {
  togglePause()
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
      confirmRhyme({ prompt: attempt.prompt, guess: attempt.guess, accepted: true })
        .then((payload) => renderRhymeAttempts(payload.attempts))
        .catch(console.error);
    });
    noBtn.addEventListener("click", () => {
      confirmRhyme({ prompt: attempt.prompt, guess: attempt.guess, accepted: false })
        .then((payload) => renderRhymeAttempts(payload.attempts))
        .catch(console.error);
    });
    actions.append(yesBtn, noBtn);
    card.append(line, actions);
    rhymeListEl.appendChild(card);
  });
}

function openRhymeModal() {
  fetchRhymeAttempts()
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
    updateConfig({ botCount: value })
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

fetchState(difficultyEl.value)
  .then(renderer.renderState)
  .catch(() => {
    startGame().catch(console.error);
  });

function pollState() {
  fetchState(difficultyEl.value)
    .then(renderer.renderState)
    .catch(console.error);
}

setInterval(pollState, 250);
