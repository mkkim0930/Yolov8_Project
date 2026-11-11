import { STATUS_LABELS } from '../constants';
import SeatIcon from './SeatIcon';

export default function SeatGrid({ seats, selectedSeatId, onSelect, loading, error }) {
  if (loading) {
    return (
      <div className="nl-seats">
        <p className="nl-message">좌석 정보를 불러오는 중입니다…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="nl-seats">
        <p className="nl-message error">{error}</p>
      </div>
    );
  }
  if (seats.length === 0) {
    return (
      <div className="nl-seats">
        <p className="nl-message">이 층에는 등록된 좌석이 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="nl-seats">
      {seats.map((seat) => (
        <button
          key={seat.id}
          className={`nl-seat ${seat.status} ${selectedSeatId === seat.id ? 'selected' : ''}`}
          onClick={() => onSelect(seat.id)}
          aria-label={`${seat.id}번 좌석, ${STATUS_LABELS[seat.status]}`}
        >
          <SeatIcon status={seat.status} />
          <div>
            <b>{seat.id}</b>
            <span>{STATUS_LABELS[seat.status]}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
