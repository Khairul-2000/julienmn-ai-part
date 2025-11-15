import os
from uuid import uuid4
from elevenlabs import ElevenLabs
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file if present


# Ensure audio is saved inside the project's audio_files directory
AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_files")
os.makedirs(AUDIO_DIR, exist_ok=True)


def textospeech(text: str) -> str:
    """Convert text to speech using ElevenLabs and save into audio_files/.

    Returns the generated filename (basename only) so it can be served via /audio/{filename}.
    Requires ELEVENLABS_API_KEY in the environment (or configure via .env).
    """

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in environment")

    client = ElevenLabs(api_key=api_key)

    audio = client.text_to_speech.convert(
        voice_id="JBFqnCBsd6RMkjVDRZzb",  # Example voice
        output_format="mp3_44100_128",
        text=text,
        model_id="eleven_multilingual_v2",
    )

    # Save the audio file inside audio_files/
    filename = f"{uuid4()}.mp3"
    file_path = os.path.join(AUDIO_DIR, filename)
    with open(file_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    print(f"Audio saved as {file_path}")
    return filename