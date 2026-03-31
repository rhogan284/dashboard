(function () {
  function update() {
    const now = new Date();
    document.getElementById('clock-time').textContent = now.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
    });
    document.getElementById('clock-date').textContent = now.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  }
  update();
  setInterval(update, 1000);
})();
