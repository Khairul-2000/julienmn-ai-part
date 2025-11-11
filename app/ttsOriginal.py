from typing import Optional, Tuple
from io import BytesIO
import logging

from app.settings import settings

EDGE_VOICE_FOR = {
    "en": "en-US-JennyNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-IsabellaNeural",
    "ar": "ar-EG-SalmaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "nl": "nl-NL-ColetteNeural",
    "pt": "pt-BR-FranciscaNeural",
    "fa": "fa-IR-DilaraNeural",
    "ur": "ur-PK-AsadNeural",
    "bn": "bn-BD-NabanitaNeural",
    "pl": "pl-PL-AgnieszkaNeural",
    "sv": "sv-SE-HilleviNeural",
    "no": "nb-NO-IselinNeural",
    "da": "da-DK-ChristelNeural",
    "fi": "fi-FI-NooraNeural",
    "hu": "hu-HU-NoemiNeural",
    "tr": "tr-TR-AhmetNeural",
    "hi": "hi-IN-SwaraNeural",
}

async def synthesize(text: str, lang: str, provider: Optional[str] = None) -> Tuple[Optional[bytes], str]:
    """Return (audio_bytes, mime). provider: 'gtts' (default) or 'edge'."""
    prov = (provider or settings.TTS_PROVIDER or "gtts").lower()
    lang = (lang or "en").lower()
    logger = logging.getLogger("app.tts")

    if prov == "gtts":
        try:
            from gtts import gTTS
            buf = BytesIO()
            gTTS(text=text, lang=lang).write_to_fp(buf)
            return buf.getvalue(), "audio/mpeg"
        except Exception as e:
            # Log the full exception with stacktrace to help debugging gTTS failures
            # keep logged text trimmed to avoid huge logs
            short_text = (text[:200] + "...") if text and len(text) > 200 else text
            logger.exception("gTTS synthesis failed (lang=%s) text=%r", lang, short_text)
            # Re-raise so the caller / web framework can surface the error during debugging
            raise
    elif prov in ("edge", "browser"): 
        try:
            import edge_tts
            voice = EDGE_VOICE_FOR.get(lang, "en-US-JennyNeural")
            fmt = "audio-24khz-48kbitrate-mono-mp3"
            communicate = edge_tts.Communicate(text, voice=voice)
            chunks = []
            async for msg in communicate.stream(format=fmt):
                if msg["type"] == "audio":
                    chunks.append(msg["data"])
            return b"".join(chunks), "audio/mpeg"
        except Exception:
            logger.exception("Edge TTS synthesis failed (lang=%s)", lang)
            raise
    else:
        return None, ""
