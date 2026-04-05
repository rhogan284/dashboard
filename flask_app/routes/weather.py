import os
import time

import httpx
from flask import Blueprint, jsonify

weather_bp = Blueprint('weather', __name__)

TOMORROW_BASE = 'https://api.tomorrow.io/v4/weather'

_cache: dict = {'data': None, 'ts': 0}
CACHE_TTL = 600  # 10 minutes

WEATHER_CODES = {
    1000: 'Clear',
    1001: 'Cloudy',
    1100: 'Mostly Clear',
    1101: 'Partly Cloudy',
    1102: 'Mostly Cloudy',
    2000: 'Fog',
    4000: 'Drizzle',
    4001: 'Rain',
    4200: 'Light Rain',
    4201: 'Heavy Rain',
    5000: 'Snow',
    5001: 'Flurries',
    5100: 'Light Snow',
    5101: 'Heavy Snow',
    6000: 'Freezing Drizzle',
    6001: 'Freezing Rain',
    7000: 'Ice Pellets',
    7101: 'Heavy Ice Pellets',
    8000: 'Thunderstorm',
}


@weather_bp.route('/api/weather')
def get_weather():
    api_key = os.getenv('TOMORROW_API_KEY', '')
    location = os.getenv('WEATHER_LOCATION', '')

    if not api_key or not location:
        return jsonify({'error': 'Weather not configured'}), 200

    now = time.time()
    if _cache['data'] and now - _cache['ts'] < CACHE_TTL:
        return jsonify(_cache['data'])

    try:
        params = {'location': location, 'units': 'metric', 'apikey': api_key}

        with httpx.Client(timeout=10) as client:
            realtime = client.get(f'{TOMORROW_BASE}/realtime', params=params).raise_for_status().json()
            forecast = client.get(f'{TOMORROW_BASE}/forecast', params={**params, 'timesteps': '1d'}).raise_for_status().json()

        values = realtime['data']['values']
        daily = forecast['timelines']['daily'][0]['values']

        data = {
            'temp': round(values['temperature']),
            'condition': WEATHER_CODES.get(values['weatherCode'], 'Unknown'),
            'high': round(daily['temperatureMax']),
            'low': round(daily['temperatureMin']),
        }

        _cache['data'] = data
        _cache['ts'] = now

        return jsonify(data)

    except Exception as exc:
        return jsonify({'error': str(exc)}), 200
