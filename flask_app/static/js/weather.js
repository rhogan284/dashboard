(function () {
  const el = document.getElementById('weather-strip');
  if (!el) return;

  const CONDITION_EMOJI = {
    'Clear': '☀️',
    'Mostly Clear': '🌤',
    'Partly Cloudy': '⛅',
    'Mostly Cloudy': '🌥',
    'Cloudy': '☁️',
    'Fog': '🌫',
    'Drizzle': '🌦',
    'Light Rain': '🌦',
    'Rain': '🌧',
    'Heavy Rain': '🌧',
    'Freezing Drizzle': '🌧',
    'Freezing Rain': '🌧',
    'Flurries': '🌨',
    'Light Snow': '🌨',
    'Snow': '❄️',
    'Heavy Snow': '❄️',
    'Ice Pellets': '🌨',
    'Heavy Ice Pellets': '🌨',
    'Thunderstorm': '⛈',
  };

  async function fetchWeather() {
    try {
      const res = await fetch('/api/weather');
      const data = await res.json();
      if (data.error || data.temp == null) {
        el.textContent = '';
        return;
      }
      const emoji = CONDITION_EMOJI[data.condition] ?? '🌡';
      el.textContent = `${data.temp}°C  ·  ${emoji} ${data.condition}  ·  H: ${data.high}°  L: ${data.low}°`;
    } catch {
      el.textContent = '';
    }
  }

  fetchWeather();
  setInterval(fetchWeather, 10 * 60 * 1000);
})();
