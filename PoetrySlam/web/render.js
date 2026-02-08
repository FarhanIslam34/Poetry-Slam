const TURN_MS = 10000;
const MAX_STACK = 16;

export function createRenderer({ elements, botIds, onBotCommit, onAutoSubmit }) {
  const {
    guessEl,
    playerCard,
    botCards,
    playerScoreEl,
    botScoreEls,
    playerToast,
    botToasts,
    timerEl,
    remainingEl,
    promptStackEl,
    pauseBtn,
    settingEls,
    botCountEl,
    evaluateBtn,
  } = elements;

  let lastEventKey = "";
  let lastTurn = "";
  let lastBotWord = "";
  let lastBotActor = "";
  let lastPrompt = "";
  let promptStack = [];
  let botTypingTimer = null;
  let botCommitInFlight = false;
  let timerRaf = null;
  let timerBaseMs = 10000;
  let timerBaseAt = 0;
  let lastTimeLeft = 1;
  let lastRoundId = null;
  let timerContextKey = "";
  let autoSubmitKey = "";
  let latestState = null;

  function updateInputState() {
    const hasText = guessEl.value.length > 0;
    guessEl.classList.toggle("has-text", hasText);
    guessEl.classList.toggle("live", latestState?.turn === "player" && !latestState?.paused);
  }

  function flashScore(actor) {
    const map = {
      player: playerScoreEl,
      bot1: botScoreEls.bot1,
      bot2: botScoreEls.bot2,
      bot3: botScoreEls.bot3,
      bot4: botScoreEls.bot4,
    };
    const el = map[actor];
    if (!el) {
      return;
    }
    el.classList.remove("score-flash");
    void el.offsetWidth;
    el.classList.add("score-flash");
    setTimeout(() => el.classList.remove("score-flash"), 900);
  }

  function animateStackTo(winner) {
    if (!promptStack.length) {
      return;
    }
    const sourceRect = promptStackEl.getBoundingClientRect();
    const targetEl = botIds.includes(winner) ? botCards[winner] : playerCard;
    const targetRect = targetEl.getBoundingClientRect();

    const fly = document.createElement("div");
    fly.className = "stack-fly";
    fly.style.left = `${sourceRect.left}px`;
    fly.style.top = `${sourceRect.top}px`;
    fly.style.width = `${sourceRect.width}px`;
    fly.style.height = `${sourceRect.height}px`;

    const inner = document.createElement("div");
    inner.className = "stack-fly-inner";
    promptStack.forEach((entry) => {
      const line = document.createElement("div");
      const actorClass = entry.actor ? ` actor-${entry.actor}` : "";
      line.className = `prompt-line${actorClass}`;
      line.textContent = entry.word;
      inner.appendChild(line);
    });
    fly.appendChild(inner);
    document.body.appendChild(fly);

    const dx = targetRect.left + targetRect.width / 2 - (sourceRect.left + sourceRect.width / 2);
    const dy = targetRect.top + targetRect.height / 2 - (sourceRect.top + sourceRect.height / 2);
    fly.animate(
      [
        { transform: "translate(0, 0) scale(1)", opacity: 1 },
        { transform: `translate(${dx}px, ${dy}px) scale(0.25)`, opacity: 0 },
      ],
      {
        duration: 800,
        easing: "cubic-bezier(0.22, 0.61, 0.36, 1)",
      }
    ).onfinish = () => {
      fly.remove();
    };
  }

  function renderState(state) {
    const currentPrompt = state.prompt || "";
    playerScoreEl.textContent = state.player_score ?? "0";
    botIds.forEach((id) => {
      botScoreEls[id].textContent = state[`${id}_score`] ?? "0";
    });
    latestState = state;

    if (typeof state.round_id === "number" && state.round_id !== lastRoundId) {
      if (lastRoundId !== null) {
        animateStackTo(state.last_actor || "player");
      }
      lastRoundId = state.round_id;
      promptStack = [];
      lastPrompt = "";
      promptStackEl.replaceChildren();
    }
    if (typeof state.remaining_rhymes === "number") {
      remainingEl.textContent =
        state.remaining_rhymes > 50
          ? "50+ remaining"
          : `${state.remaining_rhymes} remaining`;
    }

    const prevTurn = lastTurn;
    const isPlayerTurn = state.turn === "player";
    playerCard.classList.toggle("active", state.turn === "player");
    botIds.forEach((id) => {
      botCards[id].classList.toggle("active", state.turn === id);
    });
    guessEl.disabled = !isPlayerTurn || state.paused;
    if (isPlayerTurn && lastTurn !== "player") {
      guessEl.value = "";
    }
    if (!isPlayerTurn && state.turn && state.turn !== lastTurn) {
      lastBotWord = "";
      lastBotActor = "";
      guessEl.value = "";
    }
    lastTurn = state.turn || "";
    updateInputState();
    if (isPlayerTurn && !state.paused && document.activeElement !== guessEl) {
      guessEl.focus();
    }

    if (pauseBtn) {
      pauseBtn.textContent = state.paused ? "Resume" : "Pause";
    }
    if (settingEls) {
      settingEls.forEach((el) => {
        if (el) {
          el.disabled = !state.paused;
        }
      });
    }
    if (evaluateBtn) {
      evaluateBtn.disabled = !state.paused;
    }
    if (botCountEl) {
      if (document.activeElement !== botCountEl) {
        botCountEl.value = state.bot_count ?? 1;
      }
      botCountEl.disabled = !state.paused;
    }

    const botCount = typeof state.bot_count === "number" ? state.bot_count : botIds.length;
    botIds.forEach((id, index) => {
      const isActive = index < botCount;
      botCards[id].classList.toggle("is-hidden", !isActive);
    });

    const timeLeft = typeof state.time_left === "number" ? state.time_left : 1;
    const needsReset = state.turn !== prevTurn || timeLeft > lastTimeLeft + 0.02;
    lastTimeLeft = timeLeft;
    if (state.paused) {
      timerEl.textContent = "PAUSED";
      if (timerRaf) {
        cancelAnimationFrame(timerRaf);
        timerRaf = null;
      }
    }
    if (!state.paused && needsReset) {
      timerBaseMs = Math.max(0, Math.min(1, timeLeft)) * TURN_MS;
      timerBaseAt = performance.now();
      timerContextKey = `${state.round_id ?? 0}:${state.turn || ""}:${state.prompt || ""}`;
      autoSubmitKey = "";
      if (timerRaf) {
        cancelAnimationFrame(timerRaf);
        timerRaf = null;
      }
      const tick = () => {
        const elapsed = performance.now() - timerBaseAt;
        const remaining = Math.max(0, timerBaseMs - elapsed);
        timerEl.textContent = (remaining / 1000).toFixed(1);
        if (
          remaining <= 150 &&
          latestState &&
          latestState.turn === "player" &&
          !latestState.paused &&
          guessEl.value.trim() &&
          autoSubmitKey !== timerContextKey
        ) {
          autoSubmitKey = timerContextKey;
          onAutoSubmit();
        }
        if (remaining > 0) {
          timerRaf = requestAnimationFrame(tick);
        } else {
          timerRaf = null;
        }
      };
      timerRaf = requestAnimationFrame(tick);
    }

    const actor = state.last_actor || "";
    const message = state.last_event || "";
    const result = state.last_result || "info";
    const eventKey = `${actor}:${message}`;
    if (message && eventKey !== lastEventKey) {
      lastEventKey = eventKey;
      const toastMap = { player: playerToast, ...botToasts };
      const target = toastMap[actor] || playerToast;
      Object.values(toastMap).forEach((toast) => {
        if (toast !== target) {
          toast.classList.remove("show");
          toast.textContent = "";
        }
      });
      target.textContent = message;
      target.classList.toggle("bad", result === "bad");
      target.classList.toggle("good", result === "good");
      target.classList.remove("show");
      void target.offsetWidth;
      target.classList.add("show");
      if (message.startsWith("Round over.")) {
        flashScore(actor);
      }
    }

    const botWord = state.bot_word || "";
    const botActor = state.bot_actor || "";
    if (botWord !== lastBotWord || botActor !== lastBotActor) {
      lastBotWord = botWord;
      lastBotActor = botActor;
      if (botTypingTimer) {
        clearInterval(botTypingTimer);
        botTypingTimer = null;
      }
      if (botWord) {
        guessEl.value = "";
        guessEl.classList.remove("player", ...botIds);
        guessEl.classList.add(botActor || "bot1");
        updateInputState();
        let idx = 0;
        const step = Math.max(20, Math.floor(2000 / Math.max(1, botWord.length)));
        botTypingTimer = setInterval(() => {
          guessEl.value = botWord.slice(0, idx + 1).toUpperCase();
          updateInputState();
          idx += 1;
          if (idx >= botWord.length) {
            clearInterval(botTypingTimer);
            botTypingTimer = null;
            if (state.bot_pending && !botCommitInFlight) {
              botCommitInFlight = true;
              onBotCommit()
                .then(renderState)
                .catch(console.error)
                .finally(() => {
                  botCommitInFlight = false;
                });
            }
          }
        }, step);
      }
    }

    if (currentPrompt && currentPrompt !== lastPrompt) {
      lastPrompt = currentPrompt;
      const actorClass = ["player", ...botIds].includes(state.last_word_actor)
        ? state.last_word_actor
        : "";
      promptStack = [
        { word: currentPrompt.toUpperCase(), actor: actorClass },
        ...promptStack,
      ].slice(0, MAX_STACK);
      promptStackEl.replaceChildren();
      promptStack.forEach((entry, idx) => {
        const line = document.createElement("div");
        const actorTag = entry.actor ? ` actor-${entry.actor}` : "";
        line.className = idx === 0 ? `prompt-line animate${actorTag}` : `prompt-line${actorTag}`;
        line.textContent = entry.word;
        promptStackEl.appendChild(line);
      });
    }

    if (state.turn === "player") {
      guessEl.classList.remove(...botIds);
      guessEl.classList.add("player");
      updateInputState();
    } else if (!botWord) {
      guessEl.classList.remove("player", ...botIds);
      guessEl.classList.add(state.turn || "bot1");
      updateInputState();
    }
  }

  return { renderState, updateInputState };
}
