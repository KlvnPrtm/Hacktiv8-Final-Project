"""Server-only settings. Environment variables take precedence over .env."""
from dataclasses import dataclass, field
from pathlib import Path
import math
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default='', repr=False)
    model: str = 'gemini-3.5-flash'
    temperature: float = 1.0
    max_output_tokens: int = 4096
    config_error: str = ''

    @classmethod
    def load(cls, env_path: Path = ROOT / '.env'):
        load_dotenv(env_path, override=False)
        try:
            temperature = float(os.getenv('GEMINI_TEMPERATURE', '1.0'))
            tokens = int(os.getenv('GEMINI_MAX_OUTPUT_TOKENS', '4096'))
            model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash').strip()
            if not math.isfinite(temperature) or not 0 <= temperature <= 2:
                raise ValueError
            if not 256 <= tokens <= 8192 or not model or len(model) > 128:
                raise ValueError
            return cls(os.getenv('GEMINI_API_KEY', '').strip(), model, temperature, tokens)
        except ValueError:
            return cls(config_error='Periksa .env: model harus terisi, temperature 0–2, dan batas output 256–8192. Setelah diperbaiki, restart aplikasi.')
