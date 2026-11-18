// 이용 가능 좌석 / 전체 좌석 두 칸만 보여 줍니다
export default function SummaryCards({ seats, floor }) {
  const available = seats.filter((s) => s.status === 'available').length;
  return (
    <section className="nl-stats" aria-label={`${floor}층 요약`}>
      <div className="nl-stat primary">
        <p>{floor}층 이용 가능</p>
        <h2>{available}<small>석</small></h2>
      </div>
      <div className="nl-stat">
        <p>{floor}층 전체 좌석</p>
        <h2>{seats.length}<small>석</small></h2>
      </div>
    </section>
  );
}
