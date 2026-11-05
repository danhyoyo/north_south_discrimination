function rankRow(no, name, value) { const row=document.createElement('div'); row.className='rank-row'; const n=document.createElement('span'); n.className='rank-no'; n.textContent=String(no).padStart(2,'0'); const label=document.createElement('span'); label.className='rank-name'; label.textContent=name; const val=document.createElement('span'); val.className='rank-value'; val.textContent=value; row.append(n,label,val); return row; }
async function refreshOverview() {
  try {
    const [analytics,snapshot]=await Promise.all([App.get('/api/analytics'),App.get('/api/snapshot?limit=5')]);
    App.setStatus(snapshot.status); const summary=analytics.summary;
    document.getElementById('stream-name').textContent=`@${snapshot.unique_id}`; document.getElementById('stream-id').textContent=snapshot.stream_id; document.getElementById('side-stream').textContent=`@${snapshot.unique_id}`;
    document.getElementById('kpi-total').textContent=App.number(summary.total); document.getElementById('kpi-rate').textContent=App.percent(summary.discrimination_rate); document.getElementById('kpi-alert-count').textContent=`${App.number(summary.discrimination)} bình luận`; document.getElementById('kpi-confidence').textContent=App.percent(summary.average_score); document.getElementById('kpi-latency').textContent=`${summary.average_latency_ms.toFixed(0)} ms`;
    App.renderBars(document.getElementById('label-bars'),analytics.labels);
    const recent=document.getElementById('recent-comments'); recent.replaceChildren(); snapshot.comments.length ? snapshot.comments.forEach(item=>recent.append(App.commentCard(item))) : App.empty(recent);
    const users=document.getElementById('top-users'); users.replaceChildren(); analytics.top_users.length ? analytics.top_users.slice(0,6).forEach((u,i)=>users.append(rankRow(i+1,u.username,`${App.number(u.count)} bình luận`))) : App.empty(users);
    const stats=document.getElementById('collector-stats'); stats.replaceChildren(); [['Đã nhận',App.number(snapshot.status.comments_received)],['Đã phân loại',App.number(snapshot.status.classified)],['Đang chờ',App.number(snapshot.status.pending)],['Cập nhật',App.date(snapshot.status.checked_at)]].forEach((row,i)=>stats.append(rankRow(i+1,row[0],row[1])));
  } catch(error) { document.getElementById('recent-comments').textContent=`Không tải được dữ liệu: ${error}`; }
}
refreshOverview(); setInterval(refreshOverview,5000);
