"""Local Flask entrypoint. Run: python app.py"""
import bleach
import markdown
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from config import Settings
from services.gemini import ChatError, GeminiService

ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'pre', 'code',
                'blockquote', 'h1', 'h2', 'h3', 'h4', 'hr', 'a', 'table',
                'thead', 'tbody', 'tr', 'th', 'td', 'del']


def render_answer(text: str) -> str:
    rendered = markdown.markdown(text, extensions=['fenced_code', 'tables', 'sane_lists'])
    return bleach.clean(rendered, tags=ALLOWED_TAGS,
                        attributes={'a': ['href', 'title'], 'code': ['class']},
                        protocols=['http', 'https'], strip=True)


def validate_payload(data):
    def invalid(message='Pesan atau riwayat tidak valid. Muat ulang halaman lalu coba lagi.'):
        raise ChatError('invalid_request', message, 400)
    if not isinstance(data, dict):
        invalid()
    message = data.get('message')
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        invalid('Tulis pesan antara 1–4.000 karakter.')
    detail = data.get('detail', 'singkat')
    if detail not in ('singkat', 'detail'):
        invalid()
    history = data.get('history', [])
    if not isinstance(history, list) or len(history) > 100 or len(history) % 2:
        invalid()
    for i, item in enumerate(history):
        role = 'user' if i % 2 == 0 else 'assistant'
        if not isinstance(item, dict) or item.get('role') != role:
            invalid()
        content = item.get('content')
        if not isinstance(content, str) or not content.strip() or len(content) > (4000 if role == 'user' else 16000):
            invalid()
    return message.strip(), [{'role': h['role'], 'content': h['content']} for h in history[-12:]], detail


def create_app(settings=None, service=None, *, demo=False):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=512 * 1024, TRUSTED_HOSTS=['localhost', '127.0.0.1', '[::1]'])
    settings = settings if settings is not None else Settings.load()
    provider = service if service is not None else GeminiService(settings)

    @app.after_request
    def security_headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(ChatError)
    def chat_error(error):
        return jsonify(error={'code': error.code, 'message': error.message}), error.status

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return chat_error(ChatError('request_too_large', 'Percakapan terlalu besar. Mulai chat baru.', 413))

    @app.get('/')
    def index():
        return render_template('index.html', configured=bool(settings.api_key) and not settings.config_error,
                               config_error=settings.config_error, demo=demo)

    @app.post('/api/chat')
    def chat():
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            raise ChatError('forbidden', 'Permintaan harus berasal dari halaman aplikasi ini.', 403)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise ChatError('forbidden', 'Permintaan harus berasal dari halaman aplikasi ini.', 403)
        if not request.is_json:
            raise ChatError('invalid_content_type', 'Gunakan format JSON untuk request.', 415)
        try:
            data = request.get_json()
        except BadRequest:
            raise ChatError('invalid_request', 'Format JSON tidak valid.', 400) from None
        message, history, detail = validate_payload(data)
        if settings.config_error:
            raise ChatError('invalid_config', settings.config_error, 503)
        if not settings.api_key:
            raise ChatError('missing_key', 'Isi GEMINI_API_KEY di file .env, lalu restart aplikasi.', 503)
        try:
            answer = provider.reply(message, history, detail)
            return jsonify(reply=answer, html=render_answer(answer))
        except ChatError:
            raise
        except Exception:
            # Never log provider exceptions: they can contain request data or secrets.
            app.logger.warning('Chat failed with an unexpected internal error (details redacted).')
            raise ChatError('internal_error', 'Jawaban belum bisa diproses. Coba lagi atau restart aplikasi.', 500) from None

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000, debug=False)
