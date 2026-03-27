#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  BrainBack.AI — BankBot  |  First-time setup
#  Run once (needs internet to download models ~3 GB total).
#  After setup: zero internet required.
# ══════════════════════════════════════════════════════════════
set -e

CYAN='\033[0;36m'; GREEN='\033[0;32m'
YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

# Move to repo root regardless of where script is called from
cd "$(dirname "$0")/.."

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   BrainBack.AI — BankBot  (Fully Offline Setup)     ║${NC}"
echo -e "${CYAN}║   Team AlgoNexus | PS-02                            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Python ─────────────────────────────────────────────────
echo -e "${CYAN}[1/5] Checking Python 3.9+...${NC}"
python3 --version || { echo -e "${RED}❌ Python3 not found${NC}"; exit 1; }
echo -e "${GREEN}      ✅ OK${NC}\n"

# ── 2. System audio deps ──────────────────────────────────────
echo -e "${CYAN}[2/5] Installing system audio libraries...${NC}"
if command -v apt-get &>/dev/null; then
  sudo apt-get install -y -q ffmpeg espeak-ng espeak-ng-data portaudio19-dev \
    && echo -e "${GREEN}      ✅ ffmpeg + espeak-ng installed${NC}"
elif command -v brew &>/dev/null; then
  brew install ffmpeg espeak \
    && echo -e "${GREEN}      ✅ ffmpeg + espeak installed${NC}"
else
  echo -e "${YELLOW}      ⚠️  Unknown OS — install ffmpeg and espeak manually${NC}"
fi
echo ""

# ── 3. Python packages ────────────────────────────────────────
echo -e "${CYAN}[3/5] Installing Python packages...${NC}"
pip3 install -r requirements.txt -q
echo -e "${GREEN}      ✅ Python packages installed${NC}\n"

# ── 4. Ollama ─────────────────────────────────────────────────
echo -e "${CYAN}[4/5] Setting up Ollama (local LLM runtime)...${NC}"
if ! command -v ollama &>/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
  echo -e "${GREEN}      ✅ Ollama installed${NC}"
else
  echo -e "${GREEN}      ✅ Ollama already installed${NC}"
fi

# Start Ollama daemon (safe to run if already running)
nohup ollama serve &>/tmp/ollama_setup.log & sleep 3

echo "      Pulling phi3:mini model (2.3 GB — one time)..."
echo -e "${YELLOW}      This may take 5-15 min depending on your connection.${NC}"
if ollama pull phi3:mini; then
  echo -e "${GREEN}      ✅ phi3:mini ready${NC}"
else
  echo -e "${YELLOW}      ⚠️  phi3:mini failed — trying gemma2:2b...${NC}"
  ollama pull gemma2:2b || echo -e "${RED}      ❌ Pull failed. Run manually: ollama pull phi3:mini${NC}"
fi
echo ""

# ── 5. Pre-cache Whisper model ────────────────────────────────
echo -e "${CYAN}[5/5] Pre-downloading Whisper small model (244 MB)...${NC}"
python3 - <<'EOF'
from faster_whisper import WhisperModel
print("      Downloading Whisper small...")
WhisperModel("small", device="cpu", compute_type="int8")
print("      ✅ Whisper cached")
EOF
echo ""

echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ Setup complete — system is now fully offline!    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}To start the kiosk:${NC}"
echo "    bash scripts/start.sh"
echo ""
echo "  Or manually:"
echo "    ollama serve &    # terminal 1"
echo "    python3 run.py    # terminal 2"
echo ""
