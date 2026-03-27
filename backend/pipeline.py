"""
backend/pipeline.py
--------------------
Core voice pipeline — orchestrates all components end to end.

Flow:
  audio_bytes / text
      → STT (Whisper)
      → Confidence check
      → RAG retrieval (ChromaDB)
      → Confidence gate
      → LLM generation (Ollama)
      → TTS (pyttsx3)
      → PipelineResult

This module has NO Flask dependency — it can be unit-tested standalone.
"""

import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from config.prompts import SYSTEM_PROMPT, FALLBACK_MESSAGES

log = logging.getLogger("bankbot.pipeline")

# ── Banking Term Correction (STT Garbling → Correct Terms) ─────
# Whisper transliterates Hindi scheme names into garbled English.
# This dictionary maps the common misspellings to correct banking terms.
TERM_CORRECTIONS = {
    # Jan Dhan Yojana variants
    "jindan": "Jan Dhan", "jandhan": "Jan Dhan", "jandan": "Jan Dhan",
    "chandan": "Jan Dhan", "jan dan": "Jan Dhan", "jandhn": "Jan Dhan",
    "jantan": "Jan Dhan", "jendan": "Jan Dhan",
    # Yojana variants
    "yojna": "Yojana", "ehojna": "Yojana", "yogna": "Yojana",
    "yojina": "Yojana", "yojona": "Yojana",
    # Pradhan Mantri variants
    "pradhanmantri": "Pradhan Mantri", "pradhan mantree": "Pradhan Mantri",
    # Scheme name variants
    "sukanya": "Sukanya Samriddhi", "sukaniya": "Sukanya Samriddhi",
    "mudra": "Mudra loan", "mudhra": "Mudra loan",
    "kisan": "Kisan Credit Card", "kishan": "Kisan Credit Card",
    "atal": "Atal Pension", "atl": "Atal Pension",
    "vishwakarma": "PM Vishwakarma", "vishkarma": "PM Vishwakarma",
    "svanidhi": "PM SVANidhi", "swanidhi": "PM SVANidhi",
    # Banking terms
    "fd": "Fixed Deposit", "f.d.": "Fixed Deposit", "fix deposit": "Fixed Deposit",
    "rd": "Recurring Deposit", "r.d.": "Recurring Deposit",
    "kyc": "KYC documents", "k.y.c.": "KYC documents",
    "neft": "NEFT transfer", "rtgs": "RTGS transfer", "upi": "UPI payment",
    "emi": "EMI", "ppf": "PPF Public Provident Fund",
    "nps": "NPS National Pension Scheme",
    "pmjdy": "Pradhan Mantri Jan Dhan Yojana",
    "pmjjby": "Pradhan Mantri Jeevan Jyoti Bima Yojana",
    "pmsby": "Pradhan Mantri Suraksha Bima Yojana",
    "adhar": "Aadhaar", "adhan": "Aadhaar", "aadhaar": "Aadhaar",
    "aadhar": "Aadhaar",
    # Common banking verbs
    "seeds": "schemes", "seed": "scheme",
}


def normalize_query(text: str) -> str:
    """Fix common Whisper transliteration errors before RAG lookup."""
    words = text.split()
    corrected = []
    for word in words:
        clean = word.lower().strip(".,?!;:'\"")
        if clean in TERM_CORRECTIONS:
            corrected.append(TERM_CORRECTIONS[clean])
        else:
            corrected.append(word)
    result = " ".join(corrected)
    if result != text:
        print(f"\033[93m    [CORRECTION] '{text}' → '{result}'\033[0m")
    return result

# ── Zero-Latency Fast Paths (UI Mockups) ──────────────────────
FAST_PATH_CACHE = {
    "FD interest rate kya hai": {
        "en": "Our current Fixed Deposit interest rate is up to 7.1% per annum for general citizens.",
        "hi": "हमारे फिक्स्ड डिपॉजिट पर सामान्य नागरिकों के लिए 7.1% तक की ब्याज दर है।"
    },
    "savings account kholne ke liye kya chahiye": {
        "en": "To open a savings account, you need your Aadhaar card, PAN card, and 2 passport-size photos.",
        "hi": "बचत खाता खोलने के लिए आपको अपना आधार कार्ड, पैन कार्ड और 2 पासपोर्ट साइज फोटो चाहिए।"
    },
    "ATM card block karna hai": {
        "en": "I have blocked your ATM card. The new card will be dispatched to your registered address within 3 days.",
        "hi": "मैंने आपका एटीएम कार्ड ब्लॉक कर दिया है। नया कार्ड 3 दिनों के भीतर आपके पते पर भेज दिया जाएगा।"
    },
    "branch timing kya hai": {
        "en": "The branch is open from 10:00 AM to 4:00 PM on all weekdays, and up to 1:00 PM on 1st, 3rd and 5th Saturdays.",
        "hi": "शाखा सुबह 10:00 बजे से शाम 4:00 बजे तक और पहले, तीसरे और पांचवें शनिवार को दोपहर 1:00 बजे तक खुली रहती है।"
    },
    "home loan ki jankari": {
        "en": "We offer home loans starting from 8.5% interest rate with a tenure of up to 30 years.",
        "hi": "हम 8.5% ब्याज दर से शुरू होने वाले होम लोन देते हैं, जिसकी अवधि 30 साल तक होती है।"
    },
    "Jan Dhan account kya hota hai": {
        "en": "A Jan Dhan account is a zero-balance savings account providing financial access with free Rupay debit card.",
        "hi": "जन धन खाता एक जीरो-बैलेंस बचत खाता है जिसमें मुफ्त रुपे डेबिट कार्ड की सुविधा मिलती है।"
    },
    "gold loan chahiye": {
        "en": "You can pledge your gold jewelry for an instant loan with interest rates starting at 9.2%.",
        "hi": "आप अपने सोने के आभूषण गिरवी रखकर 9.2% ब्याज दर से तुरंत ऋण प्राप्त कर सकते हैं।"
    },
    "mudra loan kaise milega": {
        "en": "Mudra loans require a solid business plan and GST registration. Please visit the branch for the exact paperwork.",
        "hi": "मुद्रा लोन के लिए एक ठोस व्यापार योजना और जीएसटी पंजीकरण की आवश्यकता होती है। कागजी कार्रवाई के लिए कृपया शाखा आएं।"
    }
}

FAST_PATH_LOOKUP = {k.lower().strip(" .?!,"): k for k in FAST_PATH_CACHE.keys()}

# ── Language helpers ──────────────────────────────────────────

def detect_lang_from_text(text: str) -> str:
    """Heuristic: Devanagari codepoints → Hindi."""
    return "hi" if any('\u0900' <= c <= '\u097F' for c in text) else "en"


def compute_confidence(stt_conf: float, rag_sim: float,
                       w_stt: float = 0.45, w_rag: float = 0.55) -> float:
    return w_stt * stt_conf + w_rag * rag_sim


# ── Result dataclass ──────────────────────────────────────────

@dataclass
class PipelineResult:
    session_id:   str
    user_text:    str
    bot_text:     str
    lang:         str
    action:       str        # "answer" | "teller_alert" | "no_speech"
    confidence:   dict       = field(default_factory=dict)
    context_used: str        = ""
    audio_b64:    Optional[str] = None
    audio_format: str        = "wav"
    latency_s:    float      = 0.0
    turn:         int        = 0
    llm_model:    str        = "unknown"

    def to_dict(self) -> dict:
        return {
            "session_id":   self.session_id,
            "user_text":    self.user_text,
            "bot_text":     self.bot_text,
            "lang":         self.lang,
            "action":       self.action,
            "confidence":   self.confidence,
            "context_used": self.context_used,
            "audio_b64":    self.audio_b64,
            "audio_format": self.audio_format,
            "latency_s":    self.latency_s,
            "turn":         self.turn,
            "llm_model":    self.llm_model,
        }


# ── Pipeline ──────────────────────────────────────────────────

class VoicePipeline:
    """
    Orchestrates: STT → RAG → Confidence gate → LLM → TTS

    All component instances are injected (no tight coupling).
    """

    def __init__(self, cfg, stt, retriever, llm, tts, sessions):
        self.cfg       = cfg
        self.stt       = stt
        self.retriever = retriever
        self.llm       = llm
        self.tts       = tts
        self.sessions  = sessions

    # ── Public API ────────────────────────────────────────────

    def process_audio(self, audio_bytes: bytes, session_id: str, target_lang: str = "auto") -> PipelineResult:
        """Full pipeline from raw audio bytes."""
        t0 = time.time()
        print(f"\n\033[96m[0/4] Audio received ({len(audio_bytes)} bytes). Running Whisper STT...\033[0m")
        
        # ALWAYS transcribe in English — Hindi banking speech uses English terms
        # (home loan, KYC, FD, account, etc.) which Whisper handles better in English mode.
        # The UI language toggle only controls LLM OUTPUT language, not STT.
        stt_result = self.stt.transcribe(audio_bytes, force_language="en")

        if not stt_result.success:
            print(f"\033[91m[X] STT Failed -> No speech detected (returned to frontend)\033[0m\n")
            return PipelineResult(
                session_id=session_id,
                user_text="", bot_text="",
                lang="en", action="no_speech",
                latency_s=round(time.time() - t0, 2),
            )

        # Use target_lang for LLM output; STT is always English
        lang = "en" if target_lang == "auto" else target_lang

        return self._run(
            session_id=session_id,
            user_text=stt_result.text,
            lang=lang,
            target_lang=target_lang,
            stt_conf=stt_result.confidence,
            t0=t0,
        )

    def process_text(self, text: str, session_id: str, target_lang: str = "auto") -> PipelineResult:
        """Pipeline from plain text (sample tiles / keyboard input)."""
        t0   = time.time()
        lang = detect_lang_from_text(text) if target_lang == "auto" else target_lang

        return self._run(
            session_id=session_id,
            user_text=text,
            lang=lang,
            target_lang=target_lang,
            stt_conf=0.95,   # text input — treat as high confidence
            t0=t0,
        )

    # ── Internal orchestration ────────────────────────────────

    def _run(self, session_id: str, user_text: str,
             lang: str, target_lang: str, stt_conf: float, t0: float) -> PipelineResult:

        session = self.sessions.get(session_id)
        session.language = lang
        
        print(f"\n\033[94m==> User Input: '{user_text}'\033[0m")

        # ── FAST PATH CACHE (Zero Latency) ──
        norm_text = user_text.lower().strip(" .?!,")
        if norm_text in FAST_PATH_LOOKUP:
            print("\033[92m[⚡] Fast-Path Cache Hit -> Skipping LLM & RAG\033[0m")
            orig_key = FAST_PATH_LOOKUP[norm_text]
            ans_dict = FAST_PATH_CACHE[orig_key]
            
            reply_lang = "hi" if lang == "hi" else "en"
            bot_text = ans_dict[reply_lang]
            session.add_turn(user_text, bot_text)

            audio_b64 = None
            wav = self.tts.synthesize(bot_text, reply_lang)
            if wav:
                audio_b64 = base64.b64encode(wav).decode()

            return PipelineResult(
                session_id=session_id,
                user_text=user_text,
                bot_text=bot_text,
                lang=reply_lang,
                action="answer",
                confidence={"stt": round(stt_conf, 3), "rag": 1.0, "overall": 1.0},
                context_used="System Fast-Path Cache",
                audio_b64=audio_b64,
                audio_format="wav",
                latency_s=round(time.time() - t0, 2),
                turn=session.turn_count,
                llm_model="fast-path-cache",
            )
            print("\033[92m[✔] Pipeline Complete\033[0m\n")
            return result
   

        # 1. RAG retrieval
        corrected_text = normalize_query(user_text)
        print("\033[96m[1/4] Retrieving context from offline database (RAG)...\033[0m")
        rag_result   = self.retriever.retrieve(corrected_text)
        context_str  = "\n".join([doc for doc in rag_result.documents])
        print(f"\033[90m    [RAG] Retrieved {len(rag_result.documents)} docs | Similarity: {rag_result.similarity:.2f}\033[0m")
        for i, doc in enumerate(rag_result.documents):
            print(f"\033[90m    [RAG] Doc {i+1}: '{doc[:80]}...'\033[0m")

        # 2. Confidence gate
        stt_conf = max(0.0, min(1.0, stt_conf))
        rag_conf = rag_result.similarity
        overall_conf = compute_confidence(stt_conf, rag_conf, self.cfg.CONF_WEIGHT_STT, self.cfg.CONF_WEIGHT_RAG)
        print(f"\033[90m    [CONF] STT={stt_conf:.2f} RAG={rag_conf:.2f} Overall={overall_conf:.2f} (threshold={self.cfg.CONF_THRESHOLD})\033[0m")

        if overall_conf < self.cfg.CONF_THRESHOLD:
            print(f"\033[91m[2/4] Confidence too low ({overall_conf:.2f} < {self.cfg.CONF_THRESHOLD}) -> Routing to Human Teller.\033[0m")
            session.add_turn(user_text, "User routed to teller.")
            bot_text    = FALLBACK_MESSAGES.get(lang, FALLBACK_MESSAGES["en"])
            llm_model   = "fallback"
            action      = "teller_alert"
            context_out = ""
        else:
            print(f"\033[93m[2/4] Confidence OK ({overall_conf:.2f}). Starting LLM inference (may take 10-15s on CPU)...\033[0m")
            
            # Resolve automatic target constraints explicitly
            active_lang = lang if target_lang == "auto" else target_lang

            if active_lang == "hi":
                lang_rule = "CRITICAL RULE: Respond EXCLUSIVELY in HINDI. Your entire response MUST be written in Devanagari script."
            else:
                lang_rule = "CRITICAL RULE: Respond EXCLUSIVELY in ENGLISH. Your entire response MUST stringently be written in English characters."

            # 3. LLM Generation
            filled_prompt = SYSTEM_PROMPT.format(
                context=rag_result.context,
                language_rule=lang_rule,
            )
            print(f"\033[90m    [LLM] Context sent to model:\033[0m")
            print(f"\033[90m    {rag_result.context[:200]}...\033[0m")
            print(f"\033[90m    [LLM] User message to model: '{corrected_text}'\033[0m")
            try:
                bot_text = self.llm.generate(
                    system_prompt=filled_prompt,
                    user_text=corrected_text,
                    history=session.get_history_dicts(self.cfg.SESSION_MAX_TURNS),
                )
                print(f"\033[92m[3/4] LLM Response: '{bot_text}'\033[0m")
                action      = "answer"
                context_out = rag_result.context
                session.add_turn(user_text, bot_text)
            except Exception as e:
                log.error("LLM error: %s", e)
                bot_text    = FALLBACK_MESSAGES.get(lang, FALLBACK_MESSAGES["en"])
                action      = "teller_alert"
                context_out = ""

        # 5. TTS
        print("\033[95m[4/4] Bypassing Python Audio Compression -> Transferring to Browser TTS\033[0m")
        audio_b64 = None

        return PipelineResult(
            session_id   = session_id,
            user_text    = user_text,
            bot_text     = bot_text,
            lang         = lang,
            action       = action,
            confidence   = {
                "stt":     round(stt_conf,     3),
                "rag":     round(rag_result.similarity, 3),
                "overall": round(overall_conf, 3),
            },
            context_used = context_out,
            audio_b64    = audio_b64,
            audio_format = "wav",
            latency_s    = round(time.time() - t0, 2),
            turn         = session.turn_count,
            llm_model    = self.llm.active_model or "unavailable",
        )
        print("\033[92m[✔] Pipeline Complete\033[0m\n")
        return result
