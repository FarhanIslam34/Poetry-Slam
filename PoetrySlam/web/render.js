const TURN_MS = 10000;
const MAX_STACK = 16;

export function createRenderer({ elements, onBotCommit, onAutoSubmit }) {
  const {
    guessEl,
    playersRowEl,
    timerEl,
    remainingEl,
    rhymePartEl,
    promptStackEl,
    pauseBtn,
    settingEls,
    botCountEl,
    evaluateBtn,
  } = elements;

  const cardEls = {};
  const scoreEls = {};
  const toastEls = {};
  let activeActorClasses = [];
  let playerClassById = {};
  let playerColorById = {};
  let lastPlayerIds = [];
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
  let lastGameId = null;
  let timerContextKey = "";
  let autoSubmitKey = "";
  let latestState = null;

  function buildPlayerCards(players) {
    if (!playersRowEl) {
      return;
    }
    const ids = players.map((p) => p.id);
    if (ids.length === lastPlayerIds.length && ids.every((id, i) => id === lastPlayerIds[i])) {
      return;
    }
    lastPlayerIds = ids;
    playersRowEl.replaceChildren();
    Object.keys(cardEls).forEach((key) => delete cardEls[key]);
    Object.keys(scoreEls).forEach((key) => delete scoreEls[key]);
    Object.keys(toastEls).forEach((key) => delete toastEls[key]);

    const cardClasses = [
      "player-one",
      "player-two",
      "player-three",
      "player-four",
      "player-five",
    ];
    let botIndex = 0;
    players.forEach((player, idx) => {
      const card = document.createElement("div");
      const cardClass = cardClasses[idx] || "player-one";
      card.className = `player-card ${cardClass}`;
      card.dataset.playerId = player.id;

      const toast = document.createElement("div");
      toast.className = "turn-toast";
      card.appendChild(toast);
      toastEls[player.id] = toast;

      const avatar = document.createElement("div");
      avatar.className = `avatar ${player.avatar_class || player.id}`;
      avatar.textContent = player.is_self
        ? "YOU"
        : player.label || (player.id === "player" ? "YOU" : `BOT ${botIndex + 1}`);
      if (player.id !== "player") {
        botIndex += 1;
      }
      card.appendChild(avatar);

      const outBadge = document.createElement("div");
      outBadge.className = "out-badge";
      outBadge.textContent = "OUT";
      card.appendChild(outBadge);

      const meta = document.createElement("div");
      meta.className = "player-meta";
      const score = document.createElement("p");
      score.className = "player-score";
      score.textContent = "0";
      meta.appendChild(score);
      card.appendChild(meta);

      const colorClass = player.card_class || cardClass;
      card.classList.add(colorClass);

      playersRowEl.appendChild(card);
      cardEls[player.id] = card;
      scoreEls[player.id] = score;
      playerColorById[player.id] = colorClass;
    });
  }

  function updateInputState() {
    const hasText = guessEl.value.length > 0;
    guessEl.classList.toggle("has-text", hasText);
    const isSelfTurn = latestState?.self_id && latestState?.turn === latestState?.self_id;
    guessEl.classList.toggle("live", isSelfTurn && !latestState?.paused);
  }

  function flashScore(actor) {
    const el = scoreEls[actor];
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
    const targetEl = cardEls[winner] || cardEls.player;
    if (!targetEl) {
      return;
    }
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
    latestState = state;
    const players = Array.isArray(state.players) ? state.players : [];
    buildPlayerCards(players);
    playerClassById = Object.fromEntries(
      players.map((p) => [p.id, p.card_class || p.id])
    );
    activeActorClasses = players.map((p) => p.card_class || p.id).filter(Boolean);

    players.forEach((p) => {
      const el = scoreEls[p.id];
      if (el) {
        el.textContent = p.score ?? "0";
      }
    });

    if (typeof state.game_id === "number" && state.game_id !== lastGameId) {
      lastGameId = state.game_id;
      promptStack = [];
      lastPrompt = "";
      promptStackEl.replaceChildren();
    }
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
    if (rhymePartEl) {
      const display = state.rhyme_part_display || "";
      rhymePartEl.innerHTML = display ? `Rhyme: ${display}` : "";
    }

    const prevTurn = lastTurn;
    const isPlayerTurn = state.self_id && state.turn === state.self_id;
    const outSet = new Set(players.filter((p) => p.out).map((p) => p.id));
    Object.entries(cardEls).forEach(([id, el]) => {
      if (!el) {
        return;
      }
      el.classList.toggle("active", state.turn === id);
      el.classList.toggle("out", outSet.has(id));
    });
    guessEl.disabled = !isPlayerTurn || state.paused;
    if (state.turn !== lastTurn) {
      if (botTypingTimer) {
        clearInterval(botTypingTimer);
        botTypingTimer = null;
      }
      guessEl.value = "";
      lastBotWord = "";
      lastBotActor = "";
      guessEl.style.removeProperty("--player-color");
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

    const activeIds = new Set(players.map((p) => p.id));
    Object.entries(cardEls).forEach(([id, el]) => {
      if (!el || id === "player") {
        return;
      }
      el.classList.toggle("is-hidden", !activeIds.has(id));
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
          latestState.self_id &&
          latestState.turn === latestState.self_id &&
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
      const target = toastEls[actor] || toastEls.player;
      Object.values(toastEls).forEach((toast) => {
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
    const shouldAnimateBot = state.turn !== state.self_id && state.bot_pending;
    if (shouldAnimateBot && (botWord !== lastBotWord || botActor !== lastBotActor)) {
      lastBotWord = botWord;
      lastBotActor = botActor;
      if (botTypingTimer) {
        clearInterval(botTypingTimer);
        botTypingTimer = null;
      }
      if (botWord) {
        guessEl.value = "";
        guessEl.classList.remove("player", ...activeActorClasses);
        const botClass = playerColorById[botActor] || botActor;
        if (botClass) {
          guessEl.classList.add(botClass);
          setInputColor(botClass);
        }
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
    } else if (!shouldAnimateBot && botTypingTimer) {
      clearInterval(botTypingTimer);
      botTypingTimer = null;
    }

    if (currentPrompt && currentPrompt !== lastPrompt) {
      lastPrompt = currentPrompt;
      const actorClass = playerColorById[state.last_word_actor] || "";
      promptStack = [
        { word: currentPrompt.toUpperCase(), actor: actorClass },
        ...promptStack,
      ].slice(0, MAX_STACK);
      promptStackEl.replaceChildren();
      promptStack.forEach((entry, idx) => {
        const line = document.createElement("div");
        const actorTag = entry.actor ? " actor" : "";
        line.className = idx === 0 ? `prompt-line animate${actorTag}` : `prompt-line${actorTag}`;
        line.textContent = entry.word;
        if (entry.actor) {
          setElementColor(line, entry.actor);
        }
        promptStackEl.appendChild(line);
      });
    }

    if (state.turn === state.self_id) {
      guessEl.classList.remove(...activeActorClasses);
      const selfClass = playerColorById[state.self_id] || "player-one";
      guessEl.classList.add(selfClass);
      setInputColor(selfClass);
      updateInputState();
    } else if (!botWord) {
      guessEl.classList.remove("player", ...activeActorClasses);
      const turnClass = playerColorById[state.turn] || state.turn;
      if (turnClass) {
        guessEl.classList.add(turnClass);
        setInputColor(turnClass);
      }
      updateInputState();
    }
  }

  function setInputColor(colorClass) {
    if (!colorClass) {
      guessEl.style.removeProperty("--player-color");
      return;
    }
    guessEl.style.setProperty("--player-color", colorFromClass(colorClass));
  }

  function setElementColor(el, colorClass) {
    if (!colorClass) {
      el.style.removeProperty("--player-color");
      return;
    }
    el.style.setProperty("--player-color", colorFromClass(colorClass));
  }

  function colorFromClass(colorClass) {
    if (colorClass === "player-one") return "var(--p1)";
    if (colorClass === "player-two") return "var(--p2)";
    if (colorClass === "player-three") return "var(--p3)";
    if (colorClass === "player-four") return "var(--p4)";
    if (colorClass === "player-five") return "var(--p5)";
    return "var(--accent)";
  }

  return { renderState, updateInputState };
}
