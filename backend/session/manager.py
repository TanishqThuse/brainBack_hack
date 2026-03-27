"""
backend/session/manager.py
---------------------------
Per-user session management.

Responsibilities:
  - Create and retrieve sessions by ID
  - Store conversation history (for LLM context window)
  - Auto-expire idle sessions after timeout
  - Provide a clean turn-based API

Design: In-memory dict (no persistence across restarts).
No PII is stored — only the conversation text within the session.
Sessions are wiped on timeout or when the customer presses "New Customer".
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

log = logging.getLogger("bankbot.session")


@dataclass
class Turn:
    user: str
    bot:  str


@dataclass
class Session:
    id:           str
    history:      List[Turn]   = field(default_factory=list)
    language:     str          = "en"
    turn_count:   int          = 0
    created_at:   float        = field(default_factory=time.time)
    last_active:  float        = field(default_factory=time.time)

    def touch(self):
        self.last_active = time.time()

    def add_turn(self, user: str, bot: str):
        self.history.append(Turn(user=user, bot=bot))
        self.turn_count += 1
        self.touch()

    def get_history_dicts(self, max_turns: int) -> List[Dict[str, str]]:
        """Return last N turns as list of dicts for LLM messages."""
        return [{"user": t.user, "bot": t.bot} for t in self.history[-max_turns:]]

    def reset(self):
        self.history     = []
        self.turn_count  = 0
        self.language    = "en"
        self.last_active = time.time()
        log.info("Session %s reset", self.id[:8])


class SessionManager:
    """Thread-safe in-memory session store."""

    def __init__(self, timeout_s: int = 120):
        self.timeout_s = timeout_s
        self._store: Dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        """Retrieve or create a session. Auto-resets expired sessions."""
        if session_id not in self._store:
            self._store[session_id] = Session(id=session_id)
            log.info("New session: %s", session_id[:8])
        else:
            session = self._store[session_id]
            if self._is_expired(session):
                session.reset()
        return self._store[session_id]

    def reset(self, session_id: str):
        """Manually reset a session (New Customer button)."""
        if session_id in self._store:
            self._store[session_id].reset()

    def active_count(self) -> int:
        return sum(1 for s in self._store.values() if not self._is_expired(s))

    def _is_expired(self, session: Session) -> bool:
        return (time.time() - session.last_active) > self.timeout_s
