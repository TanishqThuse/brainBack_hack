"""
backend/routes/status.py
-------------------------
System health and model status endpoints.

Routes:
  GET /api/status   — returns loaded models, KB size, session count
  GET /api/health   — lightweight liveness probe (for watchdog / kiosk manager)
"""

import logging
from pathlib import Path
from flask import Blueprint, jsonify, current_app

log = logging.getLogger("bankbot.routes.status")

status_bp = Blueprint("status", __name__)


def _cfg():
    return current_app.config["BANKBOT_CFG"]


@status_bp.route("/status")
def status():
    """
    Detailed system status.
    Polled by the frontend every 8 seconds to update the model status bar.
    """
    cfg = _cfg()
    llm = cfg._llm
    tts = cfg._tts
    sessions = cfg._sessions

    tts_cached = len(list(cfg.TTS_CACHE_DIR.glob("*.wav")))

    return jsonify({
        "status":         "online",
        "fully_offline":  llm.active_model is not None,
        "models": {
            "stt":   f"whisper/{cfg.WHISPER_MODEL}",
            "llm":   llm.active_model or "not loaded",
            "tts":   "pyttsx3 (offline)",
            "embed": cfg.EMBED_MODEL,
        },
        "kb_entries":     len(cfg._retriever.documents) if cfg._retriever.index is not None else 0,
        "tts_cached":     tts_cached,
        "active_sessions": sessions.active_count(),
        "conf_threshold": cfg.CONF_THRESHOLD,
    })


@status_bp.route("/health")
def health():
    """Lightweight probe — returns 200 if server is up."""
    return jsonify({"status": "ok"})
