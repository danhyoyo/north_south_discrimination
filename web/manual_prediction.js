(() => {
  const form = document.getElementById('manual-form');
  const input = document.getElementById('manual-text');
  const result = document.getElementById('manual-result');
  const button = form.querySelector('button');

  input.addEventListener('input', () => result.replaceChildren());

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (button.disabled) return;

    const text = input.value;
    if (!text.trim()) {
      result.textContent = 'Vui lòng nhập nội dung bình luận.';
      input.focus();
      return;
    }

    button.disabled = true;
    input.readOnly = true;
    result.textContent = 'Đang dự đoán…';
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text}),
      });
      const prediction = await response.json();
      if (!response.ok) {
        result.textContent = prediction.error || 'Không thể dự đoán.';
        return;
      }

      const badge = document.createElement('span');
      badge.className = `badge ${App.badgeClass(prediction.label)}`;
      badge.textContent = App.labelName(prediction.label);
      const score = document.createElement('span');
      score.className = 'muted';
      score.textContent = prediction.score == null
        ? 'Bình luận không còn nội dung sau khi chuẩn hóa.'
        : `Độ tin cậy ${App.confidence(prediction.score)}`;
      result.replaceChildren(badge, score);
      if (prediction.normalized_text) {
        const normalized = document.createElement('p');
        normalized.className = 'comment-text';
        normalized.textContent = `Sau khi chuẩn hóa: ${prediction.normalized_text}`;
        result.append(normalized);
      }
    } catch {
      result.textContent = 'Không nhận được kết quả từ máy chủ. Vui lòng thử lại.';
    } finally {
      button.disabled = false;
      input.readOnly = false;
    }
  });
})();
