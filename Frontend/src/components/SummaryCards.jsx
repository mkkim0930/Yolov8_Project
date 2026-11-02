export default function SummaryCards({ seats, floor }) {
  const total = seats.length;
  const available = seats.filter((s) => s.status === 'available').length;
  const inUse = seats.filter((s) => s.status === 'inUse').length;
  const occupied = seats.filter((s) => s.status === 'occupied').length;

  return (
    <div className="summary-grid">
      <div className="summary-card">
        <div className="summary-label">전체 좌석</div>
        <div className="summary-value">
          {total}<span>석</span>
        </div>
        <p>{floor}층 전체 1인석</p>
      </div>

      <div className="summary-card">
        <div className="summary-label">이용 가능</div>
        <div className="summary-value blue-text">
          {available}<span>석</span>
        </div>
        <p>현재 이용 가능한 좌석</p>
      </div>

      <div className="summary-card">
        <div className="summary-label">사용 중</div>
        <div className="summary-value green-text">
          {inUse}<span>석</span>
        </div>
        <p>현재 사람이 이용 중인 좌석</p>
      </div>

      <div className="summary-card">
        <div className="summary-label">점유 중</div>
        <div className="summary-value orange-text">
          {occupied}<span>석</span>
        </div>
        <p>물품이 남아 있는 좌석</p>
      </div>
    </div>
  );
}
