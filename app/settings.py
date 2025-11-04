from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DEFAULT_LANG: str = "en"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    TTS_PROVIDER: str = "gtts"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

settings = Settings()

SUPPORTED_LANGS = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ru": "Russian",
    "nl": "Dutch",
    "pt": "Portuguese",
    "fa": "Persian",
    "ur": "Urdu",
    "bn": "Bengali",
    "pl": "Polish",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "hu": "Hungarian",
    "tr": "Turkish",
    "hi": "Hindi",
}