import httpx
from google import genai
from google.genai import errors, types

from config import Settings
from prompts import tutor_instruction


class ChatError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class GeminiService:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        # Injected client is used only by tests. Real clients are scoped per request.
        self.client = client

    def reply(self, message: str, history: list[dict], detail: str) -> str:
        contents = [types.Content(
            role='model' if item['role'] == 'assistant' else 'user',
            parts=[types.Part.from_text(text=item['content'])],
        ) for item in history[-12:]]
        contents.append(types.Content(role='user', parts=[types.Part.from_text(text=message)]))
        options = types.HttpOptions(timeout=60_000, retry_options=types.HttpRetryOptions(attempts=1))
        config = types.GenerateContentConfig(
            system_instruction=tutor_instruction(detail),
            temperature=self.settings.temperature,
            max_output_tokens=self.settings.max_output_tokens,
            http_options=options,
        )
        try:
            if self.client is not None:
                response = self.client.models.generate_content(model=self.settings.model, contents=contents, config=config)
            else:
                with genai.Client(api_key=self.settings.api_key, http_options=options) as client:
                    response = client.models.generate_content(model=self.settings.model, contents=contents, config=config)
        except (httpx.TimeoutException, TimeoutError):
            raise ChatError('timeout', 'Jawaban terlalu lama. Coba lagi atau ringkas pertanyaannya.', 504) from None
        except errors.APIError as exc:
            code = exc.code
            messages = {
                400: ('provider_request', 'Permintaan ditolak Gemini. Periksa model dan konfigurasi .env, lalu restart aplikasi.'),
                401: ('invalid_key', 'API key tidak valid. Periksa GEMINI_API_KEY di .env lalu restart aplikasi.'),
                403: ('invalid_key', 'API key tidak memiliki akses. Periksa key dan izin project Google AI Studio.'),
                404: ('model_unavailable', 'Model tidak tersedia untuk key ini. Periksa GEMINI_MODEL di .env lalu restart aplikasi.'),
                429: ('rate_limit', 'Kuota atau batas request Gemini tercapai. Tunggu sebentar dan periksa kuota Google AI Studio.'),
                504: ('timeout', 'Gemini belum menjawab tepat waktu. Coba lagi atau ringkas pertanyaannya.'),
            }
            error_code, message = messages.get(code, ('provider_unavailable', 'Layanan Gemini sedang bermasalah. Coba lagi sebentar lagi.'))
            # Some invalid API keys are reported by Google as HTTP 400.
            if code == 400 and 'API_KEY_INVALID' in str(getattr(exc, 'details', '')):
                error_code, message = messages[401]
            raise ChatError(error_code, message, 429 if code == 429 else 504 if code == 504 else 502) from None
        except httpx.TransportError:
            raise ChatError('connection_error', 'Tidak bisa terhubung ke Gemini. Periksa koneksi internet lalu coba lagi.') from None
        candidates = response.candidates or []
        if candidates and candidates[0].finish_reason == 'MAX_TOKENS':
            raise ChatError('response_truncated', 'Jawaban mencapai batas output. Coba mode Singkat atau pertanyaan yang lebih spesifik.')
        text = (response.text or '').strip()
        if not text:
            raise ChatError('empty_response', 'Gemini tidak memberikan jawaban teks. Coba ubah pertanyaannya.')
        if len(text) > 16000:
            raise ChatError('response_truncated', 'Jawaban terlalu panjang. Coba mode Singkat atau bagi pertanyaan menjadi beberapa bagian.')
        return text
