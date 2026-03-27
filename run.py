"""
BrainBack.AI — BankBot Voice Assistant (Fully Offline)
Team AlgoNexus | PS-02
------------------------------------------------------
Entry point. Run this to start the kiosk server.

Usage:
    python run.py
    python run.py --port 8080
    python run.py --whisper medium --llm gemma2:2b
"""

import argparse
import sys
import re
from backend.app import create_app
from backend.startup import run_startup_checks
from config.settings import Settings


class TeeWriter:
    """Duplicates all print output to both terminal and log.txt file."""
    ANSI_ESCAPE = re.compile(r'\033\[[0-9;]*m')

    def __init__(self, original, log_file):
        self.original = original
        self.log_file = log_file

    def write(self, text):
        self.original.write(text)
        # Strip ANSI color codes for clean log file
        clean = self.ANSI_ESCAPE.sub('', text)
        self.log_file.write(clean)
        self.log_file.flush()

    def flush(self):
        self.original.flush()
        self.log_file.flush()


def parse_args():
    parser = argparse.ArgumentParser(description="BrainBack.AI BankBot")
    parser.add_argument("--port",    type=int, default=5000)
    parser.add_argument("--host",    type=str, default="0.0.0.0")
    parser.add_argument("--whisper", type=str, default="small", help="Whisper model size (small recommended for noisy environments)")
    parser.add_argument("--llm",     type=str, default=None, help="Ollama model name")
    parser.add_argument("--debug",   action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()

    # Allow CLI overrides on top of settings file
    cfg = Settings()
    if args.whisper: cfg.WHISPER_MODEL  = args.whisper
    if args.llm:     cfg.OLLAMA_MODEL   = args.llm

    # ── Mirror all output to log.txt ──
    cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(cfg.LOG_DIR / "log.txt", "a", encoding="utf-8")
    log_file.write(f"\n{'='*60}\n[SESSION START]\n{'='*60}\n")
    sys.stdout = TeeWriter(sys.__stdout__, log_file)
    sys.stderr = TeeWriter(sys.__stderr__, log_file)

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   BrainBack.AI — BankBot  (FULLY OFFLINE)           ║")
    print("║   Team AlgoNexus | PS-02                            ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # Pre-flight checks + model loading
    run_startup_checks(cfg)

    # Create and run Flask app
    app = create_app(cfg)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
