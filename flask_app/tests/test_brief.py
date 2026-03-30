import json
import pytest


def test_brief_status_default_when_no_file(client):
    """Returns never_run default when brief_status.json doesn't exist."""
    response = client.get('/api/brief/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'never_run'
    assert data['generated_at'] is None
    assert data['draft_id'] is None
    assert data['error'] is None
    assert data['gmail_connected'] is False


def test_brief_status_reads_existing_file(client, app):
    """Returns data from brief_status.json when it exists."""
    status = {
        'status': 'success',
        'generated_at': '2026-03-29T07:00:00',
        'draft_id': 'draft_abc123',
        'error': None,
    }
    status_file = app.config['DATA_DIR'] / 'brief_status.json'
    status_file.write_text(json.dumps(status))

    response = client.get('/api/brief/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['draft_id'] == 'draft_abc123'


def test_brief_status_gmail_connected_when_token_exists(client, app):
    """gmail_connected is True when brief_token.json contains a refresh_token."""
    token = {
        'token': 'access_token',
        'refresh_token': 'refresh_token_value',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': 'client_id',
        'client_secret': 'client_secret',
        'scopes': ['https://www.googleapis.com/auth/gmail.readonly'],
    }
    token_file = app.config['DATA_DIR'] / 'brief_token.json'
    token_file.write_text(json.dumps(token))

    response = client.get('/api/brief/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['gmail_connected'] is True


def test_brief_preview_returns_placeholder_when_no_file(client):
    """Returns placeholder HTML when morning_brief_preview.html doesn't exist."""
    response = client.get('/api/brief/preview')
    assert response.status_code == 200
    assert b'No brief generated yet' in response.data


def test_brief_preview_serves_existing_file(client, app):
    """Serves morning_brief_preview.html when it exists."""
    preview_html = '<html><body>Test brief content</body></html>'
    preview_file = app.config['DATA_DIR'] / 'morning_brief_preview.html'
    preview_file.write_text(preview_html)

    response = client.get('/api/brief/preview')
    assert response.status_code == 200
    assert b'Test brief content' in response.data


def test_format_today_events_returns_today_only():
    """format_today_events returns only events starting today."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_today_events
    from datetime import date, timedelta
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    events = [
        {'summary': 'Today meeting', 'start': {'date': today}},
        {'summary': 'Tomorrow event', 'start': {'date': tomorrow}},
    ]
    result = format_today_events(events)
    assert 'Today meeting' in result
    assert 'Tomorrow event' not in result


def test_format_today_events_empty():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_today_events
    assert format_today_events([]) == '(nothing scheduled today)'


def test_format_week_events_excludes_today():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_week_events
    from datetime import date, timedelta
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    events = [
        {'summary': 'Today meeting', 'start': {'date': today}},
        {'summary': 'Tomorrow event', 'start': {'date': tomorrow}},
    ]
    result = format_week_events(events)
    assert 'Tomorrow event' in result
    assert 'Today meeting' not in result


def test_format_week_events_empty():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_week_events
    assert format_week_events([]) == '(no events this week)'


def test_summarise_gmail_returns_required_keys():
    """summarise_gmail returns dict with UNREAD_COUNT, ACTION_ITEMS, OTHER_EMAILS_LIST."""
    import sys, os
    from unittest.mock import patch
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import summarise_gmail

    fake_response = {
        'UNREAD_COUNT': '3',
        'ACTION_ITEMS': '<div>Reply to John</div>',
        'OTHER_EMAILS_LIST': '<div>Newsletter</div>',
    }

    import morning_brief
    with patch.object(morning_brief, '_call_ollama', return_value=fake_response):
        result = summarise_gmail({'messages': [], 'unread_count': 3})

    assert result['UNREAD_COUNT'] == '3'
    assert 'ACTION_ITEMS' in result
    assert 'OTHER_EMAILS_LIST' in result


def test_summarise_markets_returns_required_keys():
    """summarise_markets returns dict with all market/holdings keys."""
    import sys, os
    from unittest.mock import patch
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import summarise_markets

    fake_response = {
        'US_CLOSE_DATE': 'Friday 28 Mar',
        'SP500_LEVEL': '5,580', 'SP500_PCT': '-1.1%', 'SP500_COLOUR': '#ef4444',
        'NASDAQ_LEVEL': '17,322', 'NASDAQ_PCT': '-1.6%', 'NASDAQ_COLOUR': '#ef4444',
        'DOW_LEVEL': '41,583', 'DOW_PCT': '-0.7%', 'DOW_COLOUR': '#ef4444',
        'VIX': '21.7', 'VIX_INTERPRETATION': 'Elevated caution',
        'SECTOR_MOVERS': 'Energy +0.4%', 'MARKET_THEMES': 'Tariff fears',
        'AUD_RATE': '0.6281', 'AUD_PCT': '-0.4%', 'AUD_ARROW': '↓',
        'AUD_COLOUR': '#ef4444', 'AUD_CONTEXT': 'Risk-off',
        'ASX_OPEN': '-0.6%', 'ASX_COLOUR': '#ef4444', 'ASX_CONTEXT': 'SPI lower',
        'ASX_WATCH': 'BHP ex-div',
        'HOLDINGS_CONTENT': '<div>AVGO — No news</div>',
        'WEEK_EVENTS_TABLE': '<tr><td>Mon</td><td>PCE</td><td>Inflation</td></tr>',
        'HOLDINGS_EARNINGS': 'AVGO: 11 Jun',
    }

    import morning_brief
    with patch.object(morning_brief, '_call_ollama', return_value=fake_response):
        result = summarise_markets({}, 'Monday, March 30, 2026')

    required_keys = [
        'US_CLOSE_DATE', 'SP500_LEVEL', 'SP500_PCT', 'SP500_COLOUR',
        'NASDAQ_LEVEL', 'NASDAQ_PCT', 'NASDAQ_COLOUR',
        'DOW_LEVEL', 'DOW_PCT', 'DOW_COLOUR',
        'VIX', 'VIX_INTERPRETATION', 'SECTOR_MOVERS', 'MARKET_THEMES',
        'AUD_RATE', 'AUD_PCT', 'AUD_ARROW', 'AUD_COLOUR', 'AUD_CONTEXT',
        'ASX_OPEN', 'ASX_COLOUR', 'ASX_CONTEXT', 'ASX_WATCH',
        'HOLDINGS_CONTENT', 'WEEK_EVENTS_TABLE', 'HOLDINGS_EARNINGS',
    ]
    for key in required_keys:
        assert key in result, f'Missing key: {key}'
