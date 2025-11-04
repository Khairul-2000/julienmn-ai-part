# Tourist Info API

FastAPI backend that returns tourist place info (from Wikipedia) and TTS audio.  

## Run
```bash
uvicorn main:app --reload
```

## Endpoints
### 1. Lookup Place
POST /api/lookup
Body:

``` json
{ "lat": 51.8646, "lng": -0.4236, "lang": "en" }
```

### 2. Text-to-Speech
POST /api/tts
Body:

``` json
{ "text": "Hello from Paris", "lang": "en" }
```
Returns an MP3 file.

Notes
- Short summary = 5 lines
- Long summary = 15 lines
- Default language set in settings.py
