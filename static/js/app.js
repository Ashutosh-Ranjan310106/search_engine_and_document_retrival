/* ── DocRAG app.js ───────────────────────────────────────────────────────── */
(function () {
  "use strict";

  // ── Engine status polling ─────────────────────────────────────────────────
  const badge   = document.getElementById("engine-badge");
  const askBtn  = document.getElementById("ask-btn");
  let engineReady = false;

  function pollStatus() {
    fetch("/status")
      .then(r => r.json())
      .then(s => {
        if (s.ready) {
          badge.textContent = "● Ready";
          badge.className = "badge badge--ready";
          engineReady = true;
          askBtn.disabled = false;
          clearInterval(statusInterval);
        } else if (s.error) {
          badge.textContent = "✕ " + s.error.slice(0, 60);
          badge.className = "badge badge--error";
          clearInterval(statusInterval);
        } else {
          badge.textContent = "⟳ " + (s.progress || "Loading…");
        }
      })
      .catch(() => {});
  }
  pollStatus();
  const statusInterval = setInterval(pollStatus, 2000);

  // ── Mode tabs ──────────────────────────────────────────────────────────────
  let currentMode = "hybrid";
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("tab--active"));
      tab.classList.add("tab--active");
      currentMode = tab.dataset.mode;
    });
  });

  // ── Upload ─────────────────────────────────────────────────────────────────
  const dropzone   = document.getElementById("dropzone");
  const fileInput  = document.getElementById("file-input");
  const progressEl = document.getElementById("upload-progress");
  const fileList   = document.getElementById("file-list");

  function handleFiles(files) {
    if (!engineReady) { alert("Engine is not ready yet — please wait."); return; }
    if (!files.length) return;
    const fd = new FormData();
    [...files].forEach(f => fd.append("files", f));

    progressEl.textContent = "Uploading & indexing…";
    progressEl.classList.remove("hidden");

    fetch("/upload", { method: "POST", body: fd })
      .then(r => r.json())
      .then(data => {
        if (data.error) { progressEl.textContent = "Error: " + data.error; return; }
        const lines = data.results.map(r => `${r.file}: ${r.status}${r.detail ? " – " + r.detail : ""}`);
        progressEl.textContent = lines.join("\n");
        setTimeout(() => location.reload(), 1800);
      })
      .catch(err => { progressEl.textContent = "Upload failed: " + err; });
  }

  dropzone.addEventListener("dragover", e => { e.preventDefault(); dropzone.classList.add("drag-over"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
  dropzone.addEventListener("drop", e => {
    e.preventDefault(); dropzone.classList.remove("drag-over");
    handleFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener("change", () => handleFiles(fileInput.files));

  // ── Query ──────────────────────────────────────────────────────────────────
  const queryInput   = document.getElementById("query-input");
  const summariseChk = document.getElementById("summarise-toggle");
  const answerCard   = document.getElementById("answer-card");
  const answerText   = document.getElementById("answer-text");
  const answerBadge  = document.getElementById("answer-mode-badge");
  const answerLoader = document.getElementById("answer-loader");
  const copyBtn      = document.getElementById("copy-btn");
  const histSection  = document.getElementById("history-section");
  const histList     = document.getElementById("history-list");

  const history = [];

  askBtn.addEventListener("click", doQuery);
  queryInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) doQuery();
  });

  function doQuery() {
    const q = queryInput.value.trim();
    if (!q) return;

    answerCard.classList.add("hidden");
    answerLoader.classList.remove("hidden");
    askBtn.disabled = true;

    fetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: q,
        mode: currentMode,
        summarise: summariseChk.checked,
      }),
    })
      .then(r => r.json())
      .then(data => {
        answerLoader.classList.add("hidden");
        askBtn.disabled = false;

        if (data.error) {
          answerText.textContent = "Error: " + data.error;
        } else {
          answerText.textContent = data.answer;
          answerBadge.textContent = data.mode;
          answerBadge.className = "badge badge--ready";
        }
        answerCard.classList.remove("hidden");

        // Add to history
        history.unshift({ q, mode: currentMode, answer: data.answer || data.error });
        renderHistory();
      })
      .catch(err => {
        answerLoader.classList.add("hidden");
        askBtn.disabled = false;
        answerText.textContent = "Request failed: " + err;
        answerCard.classList.remove("hidden");
      });
  }

  function renderHistory() {
    if (!history.length) return;
    histSection.classList.remove("hidden");
    histList.innerHTML = "";
    history.slice(0, 10).forEach((h, i) => {
      const li = document.createElement("li");
      li.className = "history-item";
      li.innerHTML = `<div class="history-q">${escHtml(h.q)}</div>
                      <div class="history-mode">${h.mode}</div>`;
      li.addEventListener("click", () => {
        queryInput.value = h.q;
        answerText.textContent = h.answer || "";
        answerBadge.textContent = h.mode;
        answerCard.classList.remove("hidden");
      });
      histList.appendChild(li);
    });
  }

  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(answerText.textContent).then(() => {
      copyBtn.textContent = "✓";
      setTimeout(() => { copyBtn.textContent = "⎘"; }, 1500);
    });
  });

  function escHtml(s) {
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }
})();
