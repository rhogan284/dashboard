from unittest.mock import MagicMock, patch


def test_chat_streams_ollama_response(client):
    chunks = [
        b'{"response": "Hello", "done": false}\n',
        b'{"response": " world", "done": true}\n',
    ]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = iter(chunks)
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch('routes.llm.httpx.Client', return_value=mock_client):
        response = client.post('/api/chat', json={'prompt': 'Hi'})

    assert response.status_code == 200
    assert b'Hello' in response.data
    assert b' world' in response.data


def test_chat_uses_default_model_when_omitted(client):
    captured = {}
    chunks = [b'{"response": "ok", "done": true}\n']

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = iter(chunks)
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    def capture_stream(method, url, json, **kwargs):
        captured['json'] = json
        return mock_response

    mock_client = MagicMock()
    mock_client.stream = capture_stream
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch('routes.llm.httpx.Client', return_value=mock_client):
        client.post('/api/chat', json={'prompt': 'Hello'})

    assert captured['json']['model'] == 'llama3'


def test_chat_missing_prompt_returns_400(client):
    response = client.post('/api/chat', json={})
    assert response.status_code == 400
