from typing import Optional, Tuple
import logging
import os
import tempfile
import asyncio

from app.settings import settings

logger = logging.getLogger("app.tts")

async def synthesize(text: str, lang: str, provider: Optional[str] = None) -> Tuple[Optional[bytes], str]:
    """
    Simplified TTS that focuses on Edge TTS (most reliable free option)
    Falls back to a simple beep if everything fails
    """
    
    # Clean inputs
    text = text.strip()
    lang = (lang or "en").lower()
    
    if not text:
        logger.warning("Empty text provided to TTS")
        return None, ""
    
    logger.info(f"TTS Request: text='{text[:50]}...', lang={lang}, provider={provider}")
    
    # Try Edge TTS first (most reliable)
    try:
        import edge_tts
        
        # Voice mapping
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
        logger.info(f"Using Edge TTS with voice: {voice}")
        
        # Create communicate object
        communicate = edge_tts.Communicate(text, voice)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            temp_path = tmp.name
        
        try:
            await communicate.save(temp_path)
            
            # Check if file was created and has content
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, 'rb') as f:
                    audio_data = f.read()
                
                logger.info(f"Edge TTS SUCCESS: Generated {len(audio_data)} bytes")
                return audio_data, "audio/mpeg"
            else:
                logger.error("Edge TTS created empty file")
                
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.error("edge-tts not installed! Install with: pip install edge-tts")
    except Exception as e:
        logger.error(f"Edge TTS failed: {e}", exc_info=True)
    
    # Try pyttsx3 as fallback
    try:
        import pyttsx3
        
        logger.info("Trying pyttsx3 as fallback...")
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_path = tmp.name
        
        try:
            engine = pyttsx3.init()
            engine.save_to_file(text, temp_path)
            engine.runAndWait()
            
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, 'rb') as f:
                    audio_data = f.read()
                
                logger.info(f"pyttsx3 SUCCESS: Generated {len(audio_data)} bytes")
                return audio_data, "audio/wav"
                
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.warning("pyttsx3 not installed")
    except Exception as e:
        logger.warning(f"pyttsx3 failed: {e}")
    
    # Last resort: Generate a simple beep sound
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
        return audio_data, "audio/wav"
        
    except Exception as e:
        logger.error(f"Failed to generate placeholder audio: {e}")
    
    # Complete failure
    error_msg = "All TTS providers failed. Please install edge-tts: pip install edge-tts"
    logger.error(error_msg)
    raise RuntimeError(error_msg)