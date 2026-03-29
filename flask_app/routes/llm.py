import os
import httpx
from flask import Blueprint, Response, request, stream_with_context

llm_bp = Blueprint('llm', __name__)

OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
DEFAULT_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')
ALLOWED_MODELS = {DEFAULT_MODEL, 'llama3', 'mistral', 'gemma', 'phi3', 'codellama'}


@llm_bp.route('/api/chat', methods=['POST'])
def chat() -> Response:
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return Response('{"error": "prompt required"}', status=400, mimetype='application/json')

    model = data.get('model', DEFAULT_MODEL)
    if model not in ALLOWED_MODELS:
        model = DEFAULT_MODEL

    def generate():
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream(
                    'POST',
                    f'{OLLAMA_URL}/api/generate',
                    json={'model': model, 'prompt': prompt, 'stream': True},
                ) as resp:
                    resp.raise_for_status()
                    for chunk in resp.iter_bytes():
                        yield chunk
        except httpx.ConnectError:
            yield b'{"error": "Cannot connect to Ollama. Is it running?"}\n'
        except httpx.HTTPStatusError as exc:
            yield f'{{"error": "Ollama error: {exc.response.status_code}"}}\n'.encode()

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')
