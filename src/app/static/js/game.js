/* EF101-P01 Hangman - progressive enhancement for the guess/hint forms.
   The game works without JavaScript (plain form posts); with JS enabled,
   guesses update the board in place via the JSON API. */
(function () {
  "use strict";

  var tokenTag = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = tokenTag ? tokenTag.getAttribute("content") : "";

  function $(id) {
    return document.getElementById(id);
  }

  function postForm(form) {
    return fetch(form.action, {
      method: "POST",
      headers: { Accept: "application/json", "X-CSRFToken": csrfToken },
      body: new FormData(form),
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, status: response.status, data: data };
      });
    });
  }

  function renderLetters(masked) {
    var box = $("letters");
    if (!box) return;
    box.textContent = "";
    masked.forEach(function (ch) {
      var span = document.createElement("span");
      span.className = "letter";
      span.textContent = ch || "";
      box.appendChild(span);
    });
  }

  function renderGuessed(guessed) {
    var list = $("guessed-list");
    if (!list) return;
    list.textContent = "";
    if (!guessed.length) {
      var none = document.createElement("span");
      none.className = "dim";
      none.textContent = "none yet";
      list.appendChild(none);
      return;
    }
    guessed.forEach(function (letter) {
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = letter.toUpperCase();
      list.appendChild(chip);
    });
  }

  function renderHearts(remaining, max) {
    var hearts = $("hearts");
    var text = $("attempts-text");
    if (text) text.textContent = remaining + " of " + max + " attempts left";
    if (!hearts) return;
    var icons = hearts.querySelectorAll(".heart");
    icons.forEach(function (el, i) {
      if (i >= remaining) el.classList.add("lost");
      else el.classList.remove("lost");
    });
  }

  function renderParts(wrong, max) {
    var visible = Math.min(6, Math.ceil((wrong * 6) / max));
    document.querySelectorAll("#hangman-svg .part").forEach(function (el) {
      var n = parseInt(el.getAttribute("data-part"), 10);
      el.style.display = n <= visible ? "" : "none";
    });
  }

  function renderFinished(data) {
    var panel = $("result-panel");
    if (!panel) return;
    $("result-title").textContent = data.status === "won" ? "You won!" : "Game over";
    $("result-answer").textContent = data.answer || "";
    $("result-score").textContent = data.final_score;
    panel.hidden = false;
    ["guess-card", "hint-card"].forEach(function (id) {
      var card = $(id);
      if (card) card.hidden = true;
    });
  }

  function update(data) {
    renderLetters(data.masked || []);
    renderGuessed(data.guessed || []);
    renderHearts(data.remaining, data.max_attempts);
    renderParts(data.wrong, data.max_attempts);
    var score = $("score");
    if (score) score.textContent = data.score;
    var message = $("guess-message");
    if (message) message.textContent = data.message || "";
    if (data.status === "won" || data.status === "lost") renderFinished(data);
  }

  function hijack(formId, inputId) {
    var form = $(formId);
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      postForm(form).then(function (result) {
        if (!result.ok || !result.data || result.data.error) {
          form.submit(); // fall back to a full page post on errors
          return;
        }
        update(result.data);
        var input = inputId ? $(inputId) : null;
        if (input) {
          input.value = "";
          input.focus();
        }
      }).catch(function () {
        form.submit();
      });
    });
  }

  hijack("guess-form", "letter");
  hijack("hint-form", null);

  // Confirm destructive admin actions (no inline handlers, CSP-safe).
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });
})();
