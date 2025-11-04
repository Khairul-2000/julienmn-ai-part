from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os
import hashlib
import random
import time
from app.genai import enforce_lines
from app.settings import settings, SUPPORTED_LANGS
from app import wiki, genai, tts


class LookupRequest(BaseModel):
    lat: float = Field(..., description="Latitude (WGS84)")
    lng: float = Field(..., description="Longitude (WGS84)")
    lang: Optional[str] = Field(None, description="Target language (ISO 639-1)")
    radius: int = Field(8000, ge=100, le=30000, description="Search radius (m)")
    limit: int = Field(8, ge=1, le=20, description="Max candidates")


class Place(BaseModel):
    title: Optional[str]
    normalized_title: Optional[str]
    description: Optional[str]
    extract: Optional[str]
    coordinates: Dict[str, float]
    page_url: Optional[str]
    thumbnail_url: Optional[str]
    original_image_url: Optional[str]
    pageid: Optional[int]
    lang: Optional[str]
    short_summary: Optional[str]
    more_summary: Optional[str]
    ai_blurb: Optional[str] = None


class LookupResponse(BaseModel):
    best: Optional[Place]
    candidates: List[Place]


class TTSRequest(BaseModel):
    text: str
    lang: Optional[str] = None


class TTSResponse(BaseModel):
    audio_url: str
    filename: str


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


@app.post("/api/lookup", response_model=LookupResponse)
async def lookup(req: LookupRequest = Body(...)) -> LookupResponse:
    language = (req.lang or settings.DEFAULT_LANG).lower()
    if language not in SUPPORTED_LANGS:
        language = "en"

    raw = await wiki.geosearch_en(req.lat, req.lng, req.radius, req.limit)
    if not raw:
        return LookupResponse(best=None, candidates=[])

    enriched: List[Dict[str, Any]] = []
    for c in raw:
        qid = await wiki.wikidata_qid_for_pageid(c["pageid"])
        target_title = await wiki.title_in_lang_from_qid(qid, language) if qid else None

        used_en_fallback = False
        s = None
        if target_title:
            s = await wiki.summary_in_lang(target_title, language)
        if not s:
            s = await wiki.summary_in_lang(c["title"], "en")
            used_en_fallback = True
        if not s:
            continue

        place = wiki.normalize(c, s, language)

        base_short = " ".join(filter(None, [
            place.get("title"), place.get("description"), place.get("extract")
        ])).strip()

        base_more: Optional[str] = None
        if target_title:
            base_more = await wiki.full_extract(target_title, language)
        if not base_more:
            base_more = await wiki.full_extract(c["title"], "en")

        short_text = await genai.summarize_to_length(
            base_short or (base_more or ""),
            language,
            sentences=5,
            max_chars=700,
        )
        more_text = await genai.summarize_to_length(
            base_more or (place.get("extract") or ""),
            language,
            sentences=15,
            max_chars=3000,
        )

        # Summaries with enforced line limits
        place["short_summary"] = enforce_lines(short_text or (place.get("extract") or ""), 5)
        place["more_summary"] = enforce_lines(more_text or place["short_summary"], 15)

        # Translate all content to target language if not English
        if language != "en":
            if place.get("title"):
                place["title"] = await genai.translate_text(place["title"], language) or place["title"]
            if place.get("description"):
                place["description"] = await genai.translate_text(place["description"], language) or place["description"]
            if place.get("extract"):
                place["extract"] = await genai.translate_text(place["extract"], language) or place["extract"]
            if place.get("short_summary"):
                place["short_summary"] = await genai.translate_text(place["short_summary"], language) or place["short_summary"]
            if place.get("more_summary"):
                place["more_summary"] = await genai.translate_text(place["more_summary"], language) or place["more_summary"]

        enriched.append(place)

    if not enriched:
        return LookupResponse(best=None, candidates=[])

    with_img = [p for p in enriched if p.get("thumbnail_url")]
    best = (with_img or enriched)[0]

    best["ai_blurb"] = None

    best_model = Place(**best)
    
    # Return only the best match, no candidates
    return LookupResponse(best=best_model, candidates=[])


@app.post("/api/tts", response_model=TTSResponse)
async def tts_api(req: TTSRequest = Body(...)) -> TTSResponse:
    language = (req.lang or settings.DEFAULT_LANG).lower()
    if language not in SUPPORTED_LANGS:
        language = "en"

    try:
        audio, mime = await tts.synthesize(req.text.strip(), language, provider="gtts")
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err))

    if not audio:
        raise HTTPException(status_code=400, detail="gTTS synthesis failed.")

    # Generate unique filename
    text_hash = hashlib.md5(req.text.encode()).hexdigest()[:8]
    timestamp = str(int(time.time()))
    file_extension = "mp3" if "mpeg" in mime else "wav"
    random_id = str(random.randint(1002, 9999))  # Add random component
    filename = f"tts_{language}_{text_hash}_{timestamp}_{random_id}.{file_extension}"
    file_path = os.path.join(AUDIO_DIR, filename)

    # Save audio to file
    with open(file_path, "wb") as f:
        f.write(audio)

    # Return file URL
    audio_url = f"/audio/{filename}"
    return TTSResponse(audio_url=audio_url, filename=filename)


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
