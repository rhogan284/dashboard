import httpx
from flask import jsonify


def json_error(message: str, code: int, **extra):
    return jsonify({'error': message, **extra}), code


def generate_session_title(exchange: str, context: str, fallback: str) -> str:
    """Ask oMLX for a 5-8 word title for a chat session."""
    from routes.llm import OMLX_URL, OMLX_MODEL, OMLX_API_KEY, OMLX_TEMPERATURE, _strip_thinking
    prompt = (
        f"Generate a short (5-8 word) descriptive title for this {context} conversation. "
        "Return only the title, no quotes, no punctuation at the end.\n\n"
        f"{exchange}"
    )
    try:
        resp = httpx.post(
            f'{OMLX_URL}/v1/chat/completions',
            headers={'Authorization': f'Bearer {OMLX_API_KEY}'},
            json={
                'model': OMLX_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 32,
                'temperature': OMLX_TEMPERATURE,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return _strip_thinking(resp.json()['choices'][0]['message'].get('content', ''))[:100]
    except Exception:
        return fallback
