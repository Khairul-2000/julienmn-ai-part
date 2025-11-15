from typing import Optional, Tuple, List
import logging
import os
import tempfile
import asyncio
import random
import time

from app.settings import settings

logger = logging.getLogger("app.tts")

async def synthesize(text: str, lang: str, provider: Optional[str] = None, voice_id: Optional[str] = None) -> Tuple[Optional[bytes], str, str, List[str], bool]:
    """Synthesize speech.

    Order of attempts (unless provider forces a specific one):
    1. Edge TTS (websocket) with retry/backoff on transient errors (403, network)
    2. gTTS (HTTP) if installed (short texts best)
    3. pyttsx3 offline engine
    4. Generated placeholder beep (WAV)

    Returns (audio_bytes, mime_type, provider_used, attempted_sequence, beep_generated) or (None, "", "", [], False) when empty input.
    Raises RuntimeError only if all providers fail AND beep generation fails.
    """
    
    # Clean inputs
    text = text.strip()
    lang = (lang or "en").lower()
    
    if not text:
        logger.warning("Empty text provided to TTS")
        return None, "", "", [], False
    
    logger.info(f"TTS Request: text='{text[:50]}...', lang={lang}, provider={provider}")
    
    # Helper for provider ordering
    requested = (provider or "auto").lower()

    async def try_edge_tts() -> Optional[Tuple[bytes, str]]:
        try:
            import edge_tts
            from aiohttp.client_exceptions import WSServerHandshakeError

            voices = {
                "en": "en-US-JennyNeural",
                "es": "es-ES-ElviraNeural",
                "fr": "fr-FR-DeniseNeural",
                "de": "de-DE-KatjaNeural",
                "it": "it-IT-IsabellaNeural",
                "pt": "pt-BR-FranciscaNeural",
                "ru": "ru-RU-SvetlanaNeural",
                "zh": "zh-CN-XiaoxiaoNeural",
                "ja": "ja-JP-NanamiNeural",
                "ar": "ar-EG-SalmaNeural",
                "hi": "hi-IN-SwaraNeural",
                "bn": "bn-BD-NabanitaNeural",
                "ur": "ur-PK-AsadNeural",
                "fa": "fa-IR-DilaraNeural",
                "nl": "nl-NL-ColetteNeural",
                "pl": "pl-PL-AgnieszkaNeural",
                "sv": "sv-SE-HilleviNeural",
                "no": "nb-NO-IselinNeural",
                "da": "da-DK-ChristelNeural",
                "fi": "fi-FI-NooraNeural",
                "hu": "hu-HU-NoemiNeural",
                "tr": "tr-TR-AhmetNeural",
            }
            voice = voices.get(lang, "en-US-JennyNeural")
            attempts = 3
            base_delay = 0.6
            for attempt in range(1, attempts + 1):
                logger.info(f"Edge TTS attempt {attempt}/{attempts} voice={voice}")
                communicate = edge_tts.Communicate(text, voice)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    temp_path = tmp.name
                try:
                    await communicate.save(temp_path)
                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                        with open(temp_path, "rb") as f:
                            audio_data = f.read()
                        logger.info(f"Edge TTS SUCCESS bytes={len(audio_data)}")
                        return audio_data, "audio/mpeg"
                    else:
                        logger.warning("Edge TTS produced empty file; will retry")
                except WSServerHandshakeError as wse:
                    logger.warning(f"Edge TTS handshake error (likely 403) attempt={attempt}: {wse}")
                except Exception as e:
                    logger.warning(f"Edge TTS generic failure attempt={attempt}: {e}")
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                if attempt < attempts:
                    await asyncio.sleep(base_delay * attempt)
        except ImportError:
            logger.error("edge-tts not installed (pip install edge-tts)")
        except Exception as e:
            logger.error(f"Edge TTS fatal error: {e}", exc_info=True)
        return None

    async def try_gtts() -> Optional[Tuple[bytes, str]]:
        try:
            from gtts import gTTS
            # gTTS best for <= 500 chars; if longer, we chunk
            max_chunk = 400
            chunks = []
            remaining = text
            while remaining:
                chunk = remaining[:max_chunk]
                remaining = remaining[max_chunk:]
                chunks.append(chunk)
            temp_files = []
            for idx, chunk in enumerate(chunks):
                tts_obj = gTTS(chunk, lang=lang if len(lang) == 2 else "en")
                tmp = tempfile.NamedTemporaryFile(suffix=f"_{idx}.mp3", delete=False)
                temp_files.append(tmp.name)
                tmp.close()
                tts_obj.save(temp_files[-1])
            # Concatenate binary (note: naive; MP3 headers remain, but most players handle)
            audio_data = b"".join(open(f, "rb").read() for f in temp_files)
            for f in temp_files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            if audio_data:
                logger.info(f"gTTS SUCCESS bytes={len(audio_data)} chunks={len(chunks)}")
                return audio_data, "audio/mpeg"
        except ImportError:
            logger.info("gTTS not installed")
        except Exception as e:
            logger.warning(f"gTTS failed: {e}")
        return None

    async def try_pyttsx3() -> Optional[Tuple[bytes, str]]:
        try:
            import pyttsx3
            logger.info("Trying pyttsx3 fallback")
            engine = pyttsx3.init()
            engine.setProperty("rate", 180)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_path = tmp.name
            try:
                engine.save_to_file(text, temp_path)
                engine.runAndWait()
                # Ensure callbacks flush
                time.sleep(0.05)
                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                    with open(temp_path, "rb") as f:
                        audio_data = f.read()
                    logger.info(f"pyttsx3 SUCCESS bytes={len(audio_data)}")
                    return audio_data, "audio/wav"
            finally:
                try:
                    engine.stop()
                except Exception:
                    pass
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except ImportError:
            logger.info("pyttsx3 not installed")
        except Exception as e:
            logger.warning(f"pyttsx3 failed: {e}")
        return None

    async def try_elevenlabs() -> Optional[Tuple[bytes, str]]:
        """High quality voices from ElevenLabs (paid/free tier with API key).
        Requires env ELEVENLABS_API_KEY. Optionally override voice via voice_id param or ELEVENLABS_DEFAULT_VOICE_ID setting/env.
        """
        # Prefer settings (loaded from .env) then raw env for backward compatibility
        api_key = getattr(settings, "ELEVENLABS_API_KEY", "") or os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            logger.info("ElevenLabs API key not set; skipping")
            return None
        try:
            from elevenlabs import ElevenLabs  # type: ignore[import-not-found]
        except ImportError:
            logger.info("elevenlabs library not installed (pip install elevenlabs)")
            return None

        chosen_voice = voice_id or getattr(settings, "ELEVENLABS_DEFAULT_VOICE_ID", "") or os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
        logger.info(f"Trying ElevenLabs voice={chosen_voice} lang={lang}")

        def _run() -> Optional[bytes]:
            try:
                client = ElevenLabs(api_key=api_key)
                # Using streaming generator; join all chunks
                audio_gen = client.text_to_speech.convert(
                    voice_id=chosen_voice,
                    output_format="mp3_44100_128",
                    text=text,
                    model_id="eleven_multilingual_v2" if lang != "en" else "eleven_monolingual_v1"
                )
                buf = b"".join(chunk for chunk in audio_gen)
                return buf if buf else None
            except Exception as e:  # Broad catch so we don't block other providers
                logger.warning(f"ElevenLabs failed: {e}")
                return None

        try:
            audio_bytes = await asyncio.to_thread(_run)
            if audio_bytes:
                logger.info(f"ElevenLabs SUCCESS bytes={len(audio_bytes)}")
                return audio_bytes, "audio/mpeg"
        except Exception as e:
            logger.warning(f"ElevenLabs async wrapper failed: {e}")
        return None

    providers_sequence: List = []
    if requested == "edge":
        providers_sequence = [try_edge_tts]
    elif requested == "gtts":
        providers_sequence = [try_gtts]
    elif requested == "pyttsx3":
        providers_sequence = [try_pyttsx3]
    elif requested == "elevenlabs":
        providers_sequence = [try_elevenlabs]
    else:  # auto ordering: fast/free edge first, then elevenlabs (if configured), then gTTS, then offline
        providers_sequence = [try_edge_tts, try_elevenlabs, try_gtts, try_pyttsx3]

    attempted_names: List[str] = []
    for attempt_provider in providers_sequence:
        name = attempt_provider.__name__.replace("try_", "")
        attempted_names.append(name)
        result = await attempt_provider()
        if result:
            audio_data, mime_type = result
            return audio_data, mime_type, name, attempted_names, False
    
    # If all providers failed, generate beep
    
    logger.warning("All TTS providers failed, generating placeholder beep")
    
    try:
        import struct
        import math

        # Generate a 440Hz beep for 0.5 seconds
        sample_rate = 44100
        duration = 0.5
        frequency = 440

        num_samples = int(sample_rate * duration)
        samples = []

        for i in range(num_samples):
            t = float(i) / sample_rate
            value = int(32767 * math.sin(2 * math.pi * frequency * t))
            packed_value = struct.pack('<h', value)
            samples.append(packed_value)

        # Create WAV header
        wav_header = struct.pack('<4sI4s', b'RIFF', 36 + len(samples) * 2, b'WAVE')
        wav_header += struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, sample_rate,
                                  sample_rate * 2, 2, 16)
        wav_header += struct.pack('<4sI', b'data', len(samples) * 2)

        audio_data = wav_header + b''.join(samples)
        logger.info(f"Generated placeholder beep: {len(audio_data)} bytes")
        return audio_data, "audio/wav", "beep", attempted_names, True
    except Exception as e:
        logger.error(f"Failed to generate placeholder audio: {e}")
    
    # Complete failure
    error_msg = "All TTS providers failed. Please install edge-tts: pip install edge-tts"
    logger.error(error_msg)
    raise RuntimeError(error_msg)