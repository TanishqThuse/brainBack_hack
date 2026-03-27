# 🏦 BrainBack.AI — BankBot (Fully Offline)
**Team AlgoNexus | PS-02 | Hackathon Prototype**

> 100% offline voice banking assistant. No internet. No API keys. No data leaves the device.

---

## Project Structure

```
brainback/
│
├── run.py                          ← Entry point
│
├── config/
│   ├── settings.py                 ← All config (thresholds, model names, paths)
│   ├── prompts.py                  ← LLM system prompt + fallback messages
│   └── knowledge_base.py           ← 40 bank FAQs  ← EDIT THIS to add more facts
│
├── backend/
│   ├── app.py                      ← Flask factory (registers blueprints)
│   ├── startup.py                  ← Loads all models, prints health table
│   ├── pipeline.py                 ← Core orchestrator: STT→RAG→LLM→TTS
│   │
│   ├── stt/
│   │   └── whisper_engine.py       ← faster-whisper offline transcription
│   │
│   ├── rag/
│   │   ├── embedder.py             ← sentence-transformers wrapper
│   │   └── retriever.py            ← ChromaDB vector search
│   │
│   ├── llm/
│   │   └── ollama_client.py        ← Local Ollama HTTP client
│   │
│   ├── tts/
│   │   └── pyttsx_engine.py        ← pyttsx3 + espeak, WAV cache
│   │
│   ├── session/
│   │   └── manager.py              ← Per-user session + history
│   │
│   └── routes/
│       ├── voice.py                ← POST /api/query, /api/query_text, /api/reset
│       ├── status.py               ← GET  /api/status, /api/health
│       └── ui.py                   ← GET  / (serves kiosk HTML)
│
├── frontend/
│   ├── templates/index.html        ← Kiosk HTML shell
│   └── static/
│       ├── css/style.css           ← All styles
│       └── js/app.js               ← All frontend logic (modular)
│
├── scripts/
│   ├── setup.sh                    ← Linux/Mac one-time setup
│   ├── start.sh                    ← Linux/Mac daily start
│   ├── setup_windows.bat           ← Windows setup
│   └── start_windows.bat           ← Windows start
│
├── tts_cache/                      ← Auto-created: cached WAV files
├── logs/                           ← Auto-created: application logs
└── requirements.txt
```

---

## Quick Start

### Linux / Mac
```bash
bash scripts/setup.sh    # once — downloads ~3 GB of models
bash scripts/start.sh    # every time
# → open http://localhost:5000
```

### Windows
```
1. Install Ollama from https://ollama.com/download
2. Double-click scripts\setup_windows.bat
3. Double-click scripts\start_windows.bat
```

### Manual / advanced
```bash
# 1. System deps
sudo apt install ffmpeg espeak-ng espeak-ng-data   # Ubuntu
brew install ffmpeg espeak                          # macOS

# 2. Python packages
pip install -r requirements.txt

# 3. LLM model (once)
ollama pull phi3:mini        # 2.3 GB — recommended
# OR
ollama pull gemma2:2b        # 1.6 GB — lighter

# 4. Run
ollama serve &               # terminal 1
python run.py                # terminal 2
python run.py --whisper tiny --llm gemma2:2b   # lighter config
```

---

## Configuration

All settings live in `config/settings.py`:

| Setting | Default | Notes |
|---------|---------|-------|
| `WHISPER_MODEL` | `small` | `tiny` = faster, `medium` = more accurate |
| `OLLAMA_MODEL` | `phi3:mini` | or `gemma2:2b`, `mistral`, `llama3.2` |
| `CONF_THRESHOLD` | `0.35` | below this → teller fallback |
| `LLM_MAX_TOKENS` | `150` | max response length |
| `TTS_RATE` | `155` | words/min (130=slow, 175=fast) |
| `SESSION_TIMEOUT_S` | `120` | seconds idle before reset |

**To add knowledge base entries:** edit `config/knowledge_base.py` — add strings to `BANK_KNOWLEDGE`. No code changes needed.

**To change prompts / fallback messages:** edit `config/prompts.py`.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/`             | Kiosk UI |
| `POST` | `/api/query`    | Audio file → full pipeline → JSON |
| `POST` | `/api/query_text` | Text JSON → full pipeline → JSON |
| `POST` | `/api/reset`    | Reset session history |
| `GET`  | `/api/status`   | Model status + health info |
| `GET`  | `/api/health`   | Liveness probe |

### Response shape (`/api/query` and `/api/query_text`)
```json
{
  "session_id": "...",
  "user_text":  "FD rate kya hai",
  "bot_text":   "एक साल की FD पर 6.80% ब्याज मिलता है।",
  "lang":       "hi",
  "action":     "answer",
  "confidence": { "stt": 0.91, "rag": 0.74, "overall": 0.82 },
  "audio_b64":  "<base64 WAV>",
  "audio_format": "wav",
  "latency_s":  7.4,
  "turn":       1,
  "llm_model":  "phi3:mini"
}
```

---

## Demo Script (for judges)

| # | Say | Expected |
|---|-----|----------|
| 1 | "FD rate kya hai" | Hindi reply with correct rates |
| 2 | "What documents to open account?" | English: Aadhaar, PAN, photo, Rs.500 |
| 3 | "Senior citizens ke liye?" | Remembers FD context → +0.5% rate |
| 4 | "Aaj mausam kaisa hai?" | Fallback: not in KB → teller alert |
| 5 | "Jan Dhan account kya hota hai" | Hindi: PMJDY, zero balance, Aadhaar only |
| 6 | Press **New Customer** | Session wipes, fresh start |

---

## Hardware Guide

| Setup | Latency | Recommended? |
|-------|---------|-------------|
| MacBook M1/M2 16 GB | 4–7 s | ✅ Ideal for demo |
| Intel i7, 16 GB RAM | 7–12 s | ✅ Good for demo |
| Intel i5, 8 GB RAM | 12–20 s | ⚠️ Use `gemma2:2b` |
| NVIDIA GPU (6 GB VRAM) | 2–4 s | 🚀 Production speed |

For GPU: set `WHISPER_DEVICE = "cuda"` in `config/settings.py`. Ollama auto-detects CUDA.

---

*BrainBack.AI — Making banking accessible to every Indian 🇮🇳*
