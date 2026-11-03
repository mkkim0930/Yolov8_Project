import { STATUS_LABELS } from '../constants';
import { formatMinutes } from '../utils/time';

const GUIDE = {
  available: '이용 가능한 좌석입니다.',
  inUse: '현재 이용자가 사용 중입니다.',
  occupied: '이용자가 자리를 비운 상태입니다.',
};

export default function SeatDetail({
  seat,
  floor,
  seatAlerted,
  busy,
  onAlertSeat,
  onClose,
}) {
  return (
    <div className="selected-seat-info">
      <div className="seat-detail-content">
        <div className="seat-detail-heading">
          <h4>{seat.id}번 좌석</h4>
          <span className={`detail-status ${seat.status}`}>
            {STATUS_LABELS[seat.status]}
          </span>
        </div>

        <div className="seat-detail-grid">
          <div>
            <span className="detail-label">위치</span>
            <strong>{floor}층 1인석</strong>
          </div>

          <div>
            <span className="detail-label">현재 상태</span>
            <strong>{STATUS_LABELS[seat.status]}</strong>
          </div>

          <div>
            <span className="detail-label">상태 지속 시간</span>
            <strong>
              {seat.status === 'available'
                ? '-'
                : formatMinutes(seat.minutes)}
            </strong>
          </div>

          <div>
            <span className="detail-label">이용 안내</span>
            <strong>{GUIDE[seat.status]}</strong>
          </div>
        </div>

        {seat.status === 'occupied' && (
          <p className="seat-notice">
            물품이 남아 있는 상태입니다.
            점유 시간이 60분 이상 지속되면
            관리자 확인 대상이 될 수 있습니다.
          </p>
        )}

        {seat.status !== 'available' && (
          <div className="seat-detail-actions">
            <button
              className="alert-btn"
              disabled={seatAlerted || busy}
              onClick={onAlertSeat}
            >
              {seatAlerted ? '알림 설정됨' : '알림 받기'}
            </button>
          </div>
        )}
      </div>

      <button className="detail-close" onClick={onClose}>
        닫기
      </button>
    </div>
  );
}
