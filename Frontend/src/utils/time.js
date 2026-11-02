export function formatMinutes(minutes) {
  if (minutes < 60) {
    return `${minutes}분`;
  }

  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;

  return remaining === 0
    ? `${hours}시간`
    : `${hours}시간 ${remaining}분`;
}

// 서버가 준 상태 시작 시각("2026-10-31T00:10:05")으로부터 지금까지 몇 분 지났는지.
// 서버가 시간대 없이 현지 시각을 보내므로, 서버와 브라우저가 같은 시간대(한국)일 때 맞습니다.
export function minutesSince(isoString, nowMs = Date.now()) {
  const start = new Date(isoString).getTime();
  if (Number.isNaN(start)) return 0;
  return Math.max(0, Math.floor((nowMs - start) / 60000));
}

// "2026-10-31T00:10:05" -> "10월 31일 00:10"
export function formatDateTime(isoString) {
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return '-';
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${hh}:${mm}`;
}
