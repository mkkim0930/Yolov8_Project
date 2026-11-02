import { STATUS_LABELS } from '../constants';
import { formatMinutes } from '../utils/time';

export default function SeatGrid({
  seats,
  selectedSeatId,
  onSelect,
  loading,
  error,
}) {
  if (loading) {
    return (
      <div className="seat-grid">
        <p className="seat-message">좌석 정보를 불러오는 중입니다…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="seat-grid">
        <p className="seat-message error">{error}</p>
      </div>
    );
  }

  return (
    <div className="seat-grid">
      {seats.map((seat) => (
        <button
          key={seat.id}
          className={`seat-card ${seat.status} ${
            selectedSeatId === seat.id ? 'selected' : ''
          }`}
          onClick={() => onSelect(seat.id)}
        >
          <span className="seat-number">{seat.id}</span>

          <span className="seat-status">
            {STATUS_LABELS[seat.status]}
          </span>

          {seat.status === 'occupied' && (
            <span className="seat-duration">
              {formatMinutes(seat.minutes)} 경과
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
