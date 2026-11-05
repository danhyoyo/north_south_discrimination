const App = (() => {
  const number = value => new Intl.NumberFormat('vi-VN').format(Number(value || 0));
  const percent = value => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const date = value => {
    if (!value) return 'Chưa có dữ liệu';
    const parsed = new Date(value);
    return Number.isNaN(parsed.valueOf()) ? String(value) : parsed.toLocaleString('vi-VN');
  };
  const labelName = value => ({'phân biệt':'Phân biệt','ủng hộ':'Ủng hộ','khác':'Khác'})[value] || value || 'Không rõ';
  const badgeClass = value => value === 'phân biệt' ? 'discrimination' : value === 'ủng hộ' ? 'support' : '';
  async function get(url) {
    const response = await fetch(url, {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
  function setStatus(status = {}) {
    const state = status.state || 'waiting';
    document.querySelectorAll('[data-live-status]').forEach(node => {
      node.className = `live-pill ${state}`;
      const label = ({connected:'Đang LIVE',running:'Đang chạy',connecting:'Đang kết nối',waiting:'Đang chờ',disconnected:'Đã ngắt',error:'Có lỗi'})[state] || state;
      node.querySelector('[data-status-label]').textContent = label;
    });
  }
  function empty(container, title='Chưa có dữ liệu', text='Bình luận mới sẽ xuất hiện tại đây khi collector đang chạy.') {
    container.replaceChildren();
    const box = document.createElement('div'); box.className = 'empty';
    const strong = document.createElement('strong'); strong.textContent = title;
    const copy = document.createElement('span'); copy.textContent = text;
    box.append(strong, copy); container.append(box);
  }
  function renderBars(container, items, key='label') {
    container.replaceChildren();
    if (!items?.length) return empty(container);
    const max = Math.max(...items.map(item => item.count), 1);
    items.forEach(item => {
      const row = document.createElement('div'); row.className = 'bar-row';
      const name = document.createElement('span'); name.textContent = key === 'label' ? labelName(item[key]) : item[key];
      const track = document.createElement('div'); track.className = 'bar-track';
      const fill = document.createElement('div'); fill.className = `bar-fill ${item[key] === 'phân biệt' ? 'coral' : item[key] === 'ủng hộ' ? 'amber' : ''}`; fill.style.width = `${item.count / max * 100}%`;
      const count = document.createElement('strong'); count.textContent = number(item.count);
      track.append(fill); row.append(name, track, count); container.append(row);
    });
  }
  function commentCard(item) {
    const card = document.createElement('article'); card.className = 'comment-card';
    const main = document.createElement('div'); main.className = 'comment-main';
    const author = document.createElement('div'); author.className = 'comment-author'; author.textContent = item.metadata?.username || item.metadata?.unique_id || 'Người dùng TikTok';
    const text = document.createElement('div'); text.className = 'comment-text'; text.textContent = item.text || '';
    const time = document.createElement('div'); time.className = 'comment-time'; time.textContent = date(item.classified_at);
    main.append(author,text,time);
    const prediction = document.createElement('div'); prediction.className = 'prediction';
    const badge = document.createElement('span'); badge.className = `badge ${badgeClass(item.prediction?.label)}`; badge.textContent = labelName(item.prediction?.label);
    const score = document.createElement('span'); score.className = 'muted mono'; score.textContent = `Tin cậy ${percent(item.prediction?.score)}`;
    prediction.append(badge,score); card.append(main,prediction); return card;
  }
  return {number,percent,date,labelName,badgeClass,get,setStatus,empty,renderBars,commentCard};
})();
