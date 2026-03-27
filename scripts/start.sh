#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  BrainBack.AI — Start script (run this every time)
#  Usage: bash scripts/start.sh
# ══════════════════════════════════════════════════════════════
cd "$(dirname "$0")/.."

echo ""
echo "  🚀 Starting BrainBack.AI BankBot..."
echo ""

# Start Ollama server (idempotent — ok if already running)
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
  echo "  Starting Ollama server..."
  nohup ollama serve &>/tmp/ollama.log &
  sleep 2
fi

# Launch Flask app
python3 run.py
