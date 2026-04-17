/**
 * Factory that returns shared chat UI helpers bound to a specific tab's DOM elements.
 * Call once per tab: const chatUtils = createChatUtils({ historyDiv, scrollArea, ... });
 */
window.createChatUtils = function ({ historyDiv, scrollArea, thinkingDiv, timerSpan, activityLogDiv }) {
  let timerInterval = null;

  function scrollToBottom() {
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }

  function relativeDate(isoStr) {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMins = Math.floor((now - d) / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  }

  function startTimer() {
    activityLogDiv.innerHTML = '';
    const startTime = Date.now();
    thinkingDiv.classList.remove('hidden');
    timerSpan.textContent = 'Thinking\u2026 0s';
    timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      timerSpan.textContent = `Thinking\u2026 ${elapsed}s`;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    activityLogDiv.innerHTML = '';
    thinkingDiv.classList.add('hidden');
    timerSpan.textContent = 'Thinking\u2026 0s';
  }

  function logActivity(text) {
    const line = document.createElement('div');
    line.className = 'text-gray-500 text-xs';
    line.textContent = `\u2192 ${text}`;
    activityLogDiv.appendChild(line);
    scrollToBottom();
  }

  function renderHistory(messages) {
    historyDiv.innerHTML = '';
    for (const msg of messages) {
      if (msg.role === 'tool') continue;
      const bubble = document.createElement('div');
      if (msg.role === 'user') {
        bubble.className =
          'self-end bg-blue-700 text-white text-sm rounded-lg px-4 py-2 max-w-[85%] whitespace-pre-wrap';
        bubble.textContent = msg.content;
      } else {
        bubble.className =
          'self-start bg-gray-800 text-gray-100 text-sm rounded-lg px-4 py-2 max-w-[85%] prose prose-sm prose-invert max-w-none';
        bubble.innerHTML = DOMPurify.sanitize(marked.parse(msg.content));
      }
      historyDiv.appendChild(bubble);
    }
    scrollToBottom();
  }

  function makeStreamBubble() {
    const el = document.createElement('div');
    el.className =
      'self-start bg-gray-800 text-gray-100 text-sm rounded-lg px-4 py-2 max-w-[85%] prose prose-sm prose-invert max-w-none';
    historyDiv.appendChild(el);
    return el;
  }

  return { scrollToBottom, relativeDate, startTimer, stopTimer, logActivity, renderHistory, makeStreamBubble };
};
