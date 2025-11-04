from typing import Optional
import re
import google.generativeai as genai
from app.settings import settings

def enabled() -> bool:
    return bool(settings.GEMINI_API_KEY)

def _model():
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(settings.GEMINI_MODEL or "gemini-1.5-flash")

def _fallback_shorten(text: str, max_chars: int, approx_sentences: int) -> str:
    """No-Gemini fallback: approximate by sentence clipping and char cap."""
    if not text:
        return ""
    # naive sentence split
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    clipped = " ".join(parts[: max(1, approx_sentences)])
    if len(clipped) > max_chars:
        clipped = clipped[: max_chars].rsplit(" ", 1)[0] + "…"
    return clipped

async def summarize_to_length(
    text: str,
    lang: str,
    sentences: int,
    max_chars: int,
) -> Optional[str]:
    """Summarize `text` into ~`sentences` sentences (<= `max_chars`) in `lang`."""
    if not text:
        return ""
    if not enabled():
        return _fallback_shorten(text, max_chars, sentences)

    try:
        prompt = (
            "Summarize the passage below for a traveler.\n"
            f"- Write in the language with ISO code: {lang}.\n"
            f"- Aim for about {sentences} lines (short, sentence-like lines).\n"
            f"- Keep total length under {max_chars} characters.\n"
            "- Be factual; do not add new facts.\n\n"
            "PASSAGE:\n"
            f"{text}"
        )
        resp = await _model().generate_content_async(prompt)
        out = (resp.text or "").strip()
        if not out:
            return _fallback_shorten(text, max_chars, sentences)
        if len(out) > max_chars:
            out = out[: max_chars].rsplit(" ", 1)[0] + "…"
        return out
    except Exception:
        return _fallback_shorten(text, max_chars, sentences)

async def translate_text(text: str, target_lang: str) -> Optional[str]:
    """Translate to `target_lang`; return original on failure or if Gemini is off."""
    if not text:
        return ""
    if not enabled():
        return text
    try:
        prompt = (
            f"Translate into language with ISO code '{target_lang}'. "
            "Preserve meaning and names; no extra commentary.\n\n"
            f"TEXT:\n{text}"
        )
        resp = await _model().generate_content_async(prompt)
        return (resp.text or "").strip() or text
    except Exception:
        return text

def enforce_lines(text: str, lines: int) -> str:
    if not text:
        return ""
    # Split on sentence boundaries.
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    kept = parts[: max(1, lines)]
    # Join with newlines to make “lines”
    out = "\n".join(kept)
    return out 

async def make_blurb(title: str, description: str, extract: str, url: str, lang: str) -> Optional[str]:
    if not enabled():
        return None
    try:
        prompt = (
            "Write a friendly 3–4 sentence travel blurb based only on these facts. "
            "No new facts. "
            f"Respond in language ISO code: {lang}.\n\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Summary: {extract}\n"
            f"URL: {url}\n"
        )
        resp = await _model().generate_content_async(prompt)
        text = (resp.text or "").strip()
        return text or None
    except Exception:
        return None
