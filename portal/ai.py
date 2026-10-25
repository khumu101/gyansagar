"""AI Tutor: talks to the Anthropic Messages API when ANTHROPIC_API_KEY is set (no extra pip package needed)."""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = (
    "You are the AI Tutor of Gyansagar, a learning platform for students in Nepal from Nursery to PhD. "
    "Explain clearly and patiently, step by step, at the level of the student's class. "
    "Use simple English; if the student writes in Nepali, answer in Nepali. "
    "Give worked examples for maths/science. Keep answers focused (under about 300 words) and encourage the "
    "student to try the next step. Help them learn - do not just hand over answers to exam cheating requests."
)


class AIError(Exception):
    """Raised with a message that is safe to show to the student."""


def ai_enabled():
    return bool(settings.ANTHROPIC_API_KEY)


def ask_tutor(question, history=(), context=""):
    """history: iterable of (question, answer) tuples, oldest first."""
    messages = []
    for q, a in history:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": question})
    system = SYSTEM_PROMPT + (f" The student is currently studying: {context}." if context else "")
    payload = json.dumps({
        "model": settings.AI_TUTOR_MODEL,
        "max_tokens": settings.AI_TUTOR_MAX_TOKENS,
        "system": system,
        "messages": messages,
    }).encode()
    request = urllib.request.Request(API_URL, data=payload, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(request, timeout=settings.AI_TUTOR_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        logger.warning("AI tutor HTTP error %s", exc.code)
        raise AIError("The AI Tutor is busy or not set up correctly right now. Please try again later.") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("AI tutor request failed: %s", type(exc).__name__)
        raise AIError("Could not reach the AI Tutor. Please try again in a moment.") from exc
    text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text").strip()
    if not text:
        raise AIError("The AI Tutor returned an empty answer. Please rephrase your question.")
    return text
