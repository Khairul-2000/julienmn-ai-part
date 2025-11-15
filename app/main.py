from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os
from .tts import textospeech

class TTSRequest(BaseModel):
    text: str
    lang: Optional[str] = None
    translate: Optional[bool] = Field(True, description="Whether to translate text to target language before TTS")
    provider: Optional[str] = Field(None, description="Force specific TTS provider: edge, gtts, pyttsx3, elevenlabs, auto")
    voice_id: Optional[str] = Field(None, description="Optional voice ID (currently used for ElevenLabs)")


class TTSResponse(BaseModel):
    audio_url: str
    filename: str
    original_text: str
    

app = FastAPI(title="Tourist API (backend only)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create audio directory if it doesn't exist
AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_files")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Mount static files for serving audio
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")


@app.get("/")
def root():
    return {"message": "Welcome to the app API"}




@app.post("/api/tts", response_model=TTSResponse)
async def tts_api(req: TTSRequest = Body(...)) -> TTSResponse:
    """
    Enhanced TTS endpoint that can translate text before synthesis
    
    Parameters:
    - text: The text to convert to speech
    - lang: Target language for speech (and optionally translation)
    - translate: Whether to translate the text to target language first (default: True)
    """


    filename = textospeech(req.text)
    audio_url = f"/audio/{filename}"
    return TTSResponse(
        audio_url=audio_url,
        filename=filename,
        original_text=req.text,
        
    )

   

@app.get("/api/audio/{filename}")
async def get_audio_file(filename: str):
    """Serve audio file directly with proper headers"""
    file_path = os.path.join(AUDIO_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )