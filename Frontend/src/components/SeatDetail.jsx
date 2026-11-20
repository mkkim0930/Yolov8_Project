import { useEffect } from 'react';
import { STATUS_LABELS } from '../constants';
import { formatMinutes } from '../utils/time';

const GUIDE = {
  available: '바로 이용할 수 있어요.',
  inUse: '사용 중',
  occupied: '이용자는 없고 물품만 남아 있어요.',
};

// 좌석을 누르면 화면 아래에서 올라오는 상세 시트 (손가락이 닿는 위치에 큰 버튼)
export default function SeatDetail({ seat, floor, seatAlerted, busy, onAlertSeat, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const over = seat.status === 'occupied' && seat.minutes >= 60;

  return (
    <>
      <div className="nl-backdrop" onClick={onClose} />
      <div className="nl-sheet" role="dialog" aria-modal="true" aria-label={`${seat.id}번 좌석 상세`}>
        <div className="nl-grab" />
        <div className="nl-sheet-head">
          <h3>{seat.id}번 좌석</h3>
          <span className={`nl-chip ${seat.status}`}>{STATUS_LABELS[seat.status]}</span>
        </div>

        <div className="nl-facts">
          <div className="nl-fact">
            <span>위치</span>
            <strong>{floor}층 1인석</strong>
          </div>
          <div className="nl-fact">
            <span>상태 지속 시간</span>
            <strong>{seat.status === 'available' ? '-' : formatMinutes(seat.minutes)}</strong>
          </div>
          <div className="nl-fact wide">
            <span>이용 안내</span>
            <strong>{GUIDE[seat.status]}</strong>
          </div>
        </div>

        {over && (
          <p className="nl-notice strong">
            자리를 비운 지 1시간이 넘었습니다. 관리자가 좌석을 정리합니다.
          </p>
        )}
        {seat.status === 'occupied' && !over && (
          <p className="nl-notice">
            물품이 남아 있는 상태입니다. 점유 시간이 60분 이상 지속되면 관리자 확인 대상이 될 수 있습니다.
          </p>
        )}

        {seat.status === 'available' ? (
          <p className="nl-hint">이 좌석은 지금 비어 있어요.</p>
        ) : (
          <button
            className={`nl-primary ${seatAlerted ? 'done' : ''}`}
            disabled={seatAlerted || busy}
            onClick={onAlertSeat}
          >
            {seatAlerted ? '✓ 알림 설정됨' : busy ? '신청 중…' : '자리가 나면 알림 받기'}
          </button>
        )}
        <button className="nl-ghost" onClick={onClose}>닫기</button>
      </div>
    </>
  );
}
