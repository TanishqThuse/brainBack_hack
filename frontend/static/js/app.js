/**
 * BrainBack.AI — BankBot Kiosk Frontend
 * frontend/static/js/app.js
 *
 * Organised into logical sections:
 *   1. State
 *   2. Waveform visualiser
 *   3. Microphone recording
 *   4. API communication
 *   5. Response handling
 *   6. DOM helpers (messages, labels, stats)
 *   7. Status polling
 *   8. Init
 */

"use strict";

/* ─────────────────────────────────────────────────────────────
   1. STATE
   ───────────────────────────────────────────────────────────── */
const STATE = {
  sessionId:   crypto.randomUUID(),
  recording:   false,
  processing:  false,
  stream:      null,
  recorder:    null,
  chunks:      [],
  audioCtx:    null,
  analyser:    null,
  rafId:       null,
  turns:       0,
  langOverride:"auto",
};


/* ─────────────────────────────────────────────────────────────
   2. WAVEFORM VISUALISER
   ───────────────────────────────────────────────────────────── */
const Visualiser = (() => {
  const NUM_BARS = 36;
  let bars = [];

  function init() {
    const waveEl = document.getElementById("waveform");
    for (let i = 0; i < NUM_BARS; i++) {
      const b = document.createElement("div");
      b.className = "wave-bar";
      waveEl.appendChild(b);
      bars.push(b);
    }
  }

  function drawFromArray(dataArray) {
    const step = Math.floor(dataArray.length / NUM_BARS);
    bars.forEach((b, i) => {
      const v = dataArray[i * step] || 0;
      b.style.height = (4 + (v / 255) * 42) + "px";
    });
  }

  function reset() {
    bars.forEach(b => { b.style.height = "4px"; });
  }

  function start(stream) {
    if (!STATE.audioCtx) {
      STATE.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    STATE.analyser = STATE.audioCtx.createAnalyser();
    STATE.analyser.fftSize = 256;
    STATE.audioCtx.createMediaStreamSource(stream).connect(STATE.analyser);

    const data = new Uint8Array(STATE.analyser.frequencyBinCount);
    const loop = () => {
      STATE.rafId = requestAnimationFrame(loop);
      STATE.analyser.getByteFrequencyData(data);
      drawFromArray(data);
    };
    loop();
    document.getElementById("waveform").classList.add("active");
  }

  function stop() {
    if (STATE.rafId) cancelAnimationFrame(STATE.rafId);
    reset();
    document.getElementById("waveform").classList.remove("active");
  }

  return { init, start, stop };
})();


/* ─────────────────────────────────────────────────────────────
   3. MICROPHONE RECORDING
   ───────────────────────────────────────────────────────────── */
const Recorder = (() => {

  async function start() {
    try {
      STATE.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate:        48000,
          channelCount:      1,
          echoCancellation:  true,
          noiseSuppression:  true,
          autoGainControl:   true,
        },
      });
    } catch (e) {
      UI.setLabel("❌ Microphone access denied", "error");
      return;
    }

    STATE.chunks = [];

    // Pick best supported MIME type
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4", ""]
      .find(t => !t || MediaRecorder.isTypeSupported(t));

    STATE.recorder = new MediaRecorder(STATE.stream, mime ? { mimeType: mime } : {});
    STATE.recorder.ondataavailable = e => { if (e.data.size > 0) STATE.chunks.push(e.data); };
    STATE.recorder.onstop = API.sendAudio;
    STATE.recorder.start(100);

    STATE.recording = true;
    UI.setRecordingState(true);
    Visualiser.start(STATE.stream);
    UI.setLabel("🔴 Recording… tap to stop", "active");
    document.getElementById("teller-alert").classList.remove("visible");
  }

  function stop() {
    if (!STATE.recorder) return;
    STATE.recorder.stop();
    STATE.stream.getTracks().forEach(t => t.stop());
    STATE.recording = false;
    Visualiser.stop();
    UI.setRecordingState(false);
    UI.setLabel("⏳ Processing…", "active");
    UI.setProcessing(true);
  }

  return { start, stop };
})();


/* ─────────────────────────────────────────────────────────────
   4. API COMMUNICATION
   ───────────────────────────────────────────────────────────── */
const API = (() => {

  async function sendAudio() {
    const blob = new Blob(STATE.chunks, { type: STATE.recorder.mimeType || "audio/webm" });
    const fd   = new FormData();
    fd.append("audio",      blob, "query.webm");
    fd.append("session_id", STATE.sessionId);
    fd.append("language",   STATE.langOverride);

    UI.showThinking(true);
    try {
      const res  = await fetch("/api/query", { method: "POST", body: fd });
      const data = await res.json();
      UI.showThinking(false);
      ResponseHandler.handle(data);
    } catch (err) {
      UI.showThinking(false);
      UI.setLabel("❌ Server error — please try again", "error");
      UI.setProcessing(false);
      console.error("Audio query error:", err);
    }
  }

  async function sendText(text) {
    UI.showThinking(true);
    try {
      const res  = await fetch("/api/query_text", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ text, session_id: STATE.sessionId, language: STATE.langOverride }),
      });
      const data = await res.json();
      UI.showThinking(false);
      ResponseHandler.handle(data);
    } catch (err) {
      UI.showThinking(false);
      UI.setLabel("❌ Server error", "error");
      console.error("Text query error:", err);
    }
  }

  async function resetSession() {
    try {
      await fetch("/api/reset", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ session_id: STATE.sessionId }),
      });
    } catch (_) {}
  }

  async function fetchStatus() {
    try {
      const res  = await fetch("/api/status");
      const data = await res.json();
      StatusBar.update(data);
    } catch (_) {}
  }

  return { sendAudio, sendText, resetSession, fetchStatus };
})();


/* ─────────────────────────────────────────────────────────────
   5. RESPONSE HANDLING
   ───────────────────────────────────────────────────────────── */
const ResponseHandler = (() => {

  function handle(data) {
    UI.setProcessing(false);
    UI.setLabel("Tap to speak &nbsp;•&nbsp; बोलने के लिए टैप करें", "");

    if (data.status === "no_speech") {
      UI.setLabel("🔇 No speech detected — please try again", "error");
      return;
    }
    if (data.error) {
      UI.setLabel("❌ " + data.error, "error");
      return;
    }

    // Update stats
    STATE.turns = data.turn || STATE.turns + 1;
    UI.updateStats({
      turns:   STATE.turns,
      conf:    Math.round((data.confidence?.overall || 0) * 100) + "%",
      lang:    data.lang === "hi" ? "हिंदी" : "English",
      latency: (data.latency_s || 0).toFixed(1) + "s",
    });

    // Remove hard-coded language badge update, as the user manually toggles it now.
    // document.getElementById("lang-badge").textContent =
    //   data.lang === "hi" ? "🇮🇳 हिंदी" : "🇬🇧 English";

    // Add conversation messages
    UI.addMessage("user", data.user_text, null, false);
    UI.addMessage("bot",  data.bot_text, data.confidence, data.action === "teller_alert");

    // Teller alert
    if (data.action === "teller_alert") {
      UI.showTellerAlert(data.bot_text);
    }

    // Play TTS audio
    if (data.audio_b64) {
      const fmt    = data.audio_format || "wav";
      const player = document.getElementById("audio-player");
      player.src   = `data:audio/${fmt};base64,${data.audio_b64}`;
      player.play().catch(() => {});  // autoplay may be blocked — silent fail
    } else if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(data.bot_text);
      const targetLang = data.lang === "hi" ? "hi" : "en";
      utterance.lang = targetLang === "hi" ? "hi-IN" : "en-IN";
      utterance.rate = 0.95;
      
      // Try to find the best matching voice for the language
      const voices = window.speechSynthesis.getVoices();
      const matchVoice = voices.find(v => v.lang.startsWith(targetLang));
      if (matchVoice) utterance.voice = matchVoice;
      
      window.speechSynthesis.speak(utterance);
    }

    // Update debug panel
    document.getElementById("debug-panel").textContent = JSON.stringify({
      user_text:    data.user_text,
      bot_text:     data.bot_text,
      lang:         data.lang,
      confidence:   data.confidence,
      action:       data.action,
      llm_model:    data.llm_model,
      latency_s:    data.latency_s,
      ctx_preview:  (data.context_used || "").slice(0, 250) + "…",
    }, null, 2);

    // Show exit prompt if it was a valid turn
    if (data.action !== "no_speech") {
      document.getElementById('exit-prompt').classList.add('visible');
    }
  }

  return { handle };
})();


/* ─────────────────────────────────────────────────────────────
   6. DOM HELPERS
   ───────────────────────────────────────────────────────────── */
const UI = (() => {

  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function removeEmptyState() {
    const el = document.getElementById("empty-state");
    if (el) el.remove();
  }

  function addMessage(role, text, conf, isFallback) {
    removeEmptyState();
    const convo = document.getElementById("conversation");

    const wrap = document.createElement("div");
    wrap.className = `msg ${role}${isFallback ? " fallback" : ""}`;

    let metaHTML = "";
    if (role === "bot" && conf) {
      const pct = Math.round(conf.overall * 100);
      const cls = pct >= 60 ? "conf-hi" : pct >= 38 ? "conf-med" : "conf-lo";
      metaHTML = `
        <div class="msg-meta">
          <span class="conf-badge ${cls}">${pct}% conf</span>
          <span>STT ${Math.round(conf.stt * 100)}%</span>
          <span>RAG ${Math.round(conf.rag * 100)}%</span>
        </div>`;
    }

    wrap.innerHTML = `
      <div class="avatar">${role === "user" ? "👤" : "🤖"}</div>
      <div>
        <div class="bubble">${escHtml(text)}</div>
        ${metaHTML}
      </div>`;

    convo.appendChild(wrap);
    convo.scrollTop = convo.scrollHeight;
  }

  function showThinking(visible) {
    const el = document.getElementById("thinking-wrap");
    el.classList.toggle("visible", visible);
    const convo = document.getElementById("conversation");
    convo.scrollTop = convo.scrollHeight;
  }

  function showTellerAlert(msg) {
    const el   = document.getElementById("teller-alert");
    const body = document.getElementById("teller-msg");
    body.textContent = msg;
    el.classList.add("visible");
    setTimeout(() => el.classList.remove("visible"), 14000);
  }

  function setRecordingState(recording) {
    const btn = document.getElementById("mic-btn");
    btn.classList.toggle("recording", recording);
    ["mic-ring-1", "mic-ring-2", "mic-ring-3"].forEach(id => {
      document.getElementById(id).classList.toggle("off", !recording);
    });
  }

  function setProcessing(processing) {
    STATE.processing = processing;
    const btn = document.getElementById("mic-btn");
    btn.classList.toggle("processing", processing);
    btn.disabled   = processing;
    btn.textContent = processing ? "⏳" : "🎙️";

    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");
    if (chatInput) chatInput.disabled = processing;
    if (sendBtn) sendBtn.disabled = processing;
  }

  function setLabel(html, type) {
    const el = document.getElementById("mic-label");
    el.innerHTML   = html;
    el.className   = `mic-label${type ? " " + type : ""}`;
  }

  function updateStats({ turns, conf, lang, latency }) {
    document.getElementById("stat-turns").textContent   = turns;
    document.getElementById("stat-conf").textContent    = conf;
    document.getElementById("stat-lang").textContent    = lang;
    document.getElementById("stat-latency").textContent = latency;
  }

  return {
    addMessage, showThinking, showTellerAlert,
    setRecordingState, setProcessing, setLabel, updateStats,
  };
})();


/* ─────────────────────────────────────────────────────────────
   7. STATUS BAR POLLING
   ───────────────────────────────────────────────────────────── */
const StatusBar = (() => {
  function update(data) {
    const row = document.getElementById("model-bar");
    if (!row) return;

    const tag = (label, on) =>
      `<span class="model-tag ${on ? "mt-on" : "mt-off"}">${label}</span>`;
    const sep = `<span class="mt-sep">|</span>`;

    const llmOk = data.models?.llm && data.models.llm !== "not loaded";

    row.innerHTML = [
      `<span class="mt-lbl">STT:</span> ${tag("Whisper " + (data.models?.stt?.split("/")[1] || ""), true)}`,
      sep,
      `<span class="mt-lbl">LLM:</span> ${tag(data.models?.llm || "Not loaded", llmOk)}`,
      sep,
      `<span class="mt-lbl">TTS:</span> ${tag("pyttsx3", true)}`,
      sep,
      `<span class="mt-lbl">KB:</span>  ${tag(data.kb_entries + " FAQs", true)}`,
      sep,
      data.fully_offline ? tag("🔒 FULLY OFFLINE", true) : tag("⚠ LLM missing", false),
    ].join(" ");
  }

  function startPolling() {
    API.fetchStatus();
    setInterval(API.fetchStatus, 8000);
  }

  return { update, startPolling };
})();


/* ─────────────────────────────────────────────────────────────
   8. PUBLIC EVENT HANDLERS (called from HTML onclick)
   ───────────────────────────────────────────────────────────── */

window.startSession = function(lang) {
  STATE.sessionId = crypto.randomUUID();
  STATE.langOverride = lang;
  STATE.turns = 0;
  
  document.getElementById('welcome-overlay').style.display = 'none';
  document.getElementById('main-ui').style.display = 'flex';
  
  const modes = [
    { id: "auto", label: "🌐 Auto-Detect" },
    { id: "hi",   label: "🇮🇳 Hindi Only" },
    { id: "en",   label: "🇬🇧 English Only" }
  ];
  const selectedMode = modes.find(m => m.id === lang) || modes[0];
  document.getElementById("lang-badge").textContent = selectedMode.label;
  
  // Optional: prompt the user to speak
  UI.addMessage("bot", lang === 'hi' ? "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?" : "Hello! How can I help you?", null, false);
};

window.endSession = async function() {
  await window.resetSession();
};

window.hideExitPrompt = function() {
  document.getElementById('exit-prompt').classList.remove('visible');
};

window.toggleMic = function () {
  if (STATE.processing) return;
  STATE.recording ? Recorder.stop() : Recorder.start();
};

window.toggleLanguageOverride = function() {
  const modes = [
    { id: "auto", label: "🌐 Auto-Detect" },
    { id: "hi",   label: "🇮🇳 Hindi Only" },
    { id: "en",   label: "🇬🇧 English Only" }
  ];
  let currIdx = modes.findIndex(m => m.id === STATE.langOverride);
  let nextIdx = (currIdx + 1) % modes.length;
  STATE.langOverride = modes[nextIdx].id;
  document.getElementById("lang-badge").textContent = modes[nextIdx].label;
};

window.askSample = function (text) {
  // Show user message immediately, then query
  UI.addMessage("user", text, null, false);
  API.sendText(text);
};

window.submitTextQuery = function () {
  if (STATE.processing) return;
  const inputEl = document.getElementById("chat-input");
  const text = inputEl.value.trim();
  if (!text) return;

  inputEl.value = "";
  // Show user message immediately, then query
  UI.addMessage("user", text, null, false);
  API.sendText(text);
};

window.resetSession = async function () {
  await API.resetSession();
  location.reload();
};

window.toggleDebug = function () {
  document.getElementById("debug-panel").classList.toggle("visible");
};


/* ─────────────────────────────────────────────────────────────
   INIT — runs on DOMContentLoaded
   ───────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  Visualiser.init();
  StatusBar.startPolling();

  const chatInput = document.getElementById("chat-input");
  if (chatInput) {
    chatInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        window.submitTextQuery();
      }
    });
  }

  const sendBtn = document.getElementById("send-btn");
  if (sendBtn) {
    sendBtn.addEventListener("click", window.submitTextQuery);
  }
});
