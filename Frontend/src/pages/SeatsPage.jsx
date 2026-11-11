import { useCallback, useState } from 'react';
import { subscribeToAlert } from '../api';
import useFloorSeats from '../hooks/useFloorSeats';
import FloorTabs from '../components/FloorTabs';
import SummaryCards from '../components/SummaryCards';
import SeatGrid from '../components/SeatGrid';
import SeatDetail from '../components/SeatDetail';
import AlertModal from '../components/AlertModal';

// subscribeToAlert 가 던지는 오류 코드별 안내 문구
const ALERT_ERRORS = {
  'ios-install':
    "아이폰은 공유 버튼 → '홈 화면에 추가'를 한 뒤, 홈 화면 아이콘으로 열어야 알림을 받을 수 있어요.",
  unsupported: '이 브라우저는 푸시 알림을 지원하지 않아요.',
  denied:
    '브라우저 알림 권한이 꺼져 있어요. 설정에서 이 사이트의 알림을 허용해 주세요.',
  'server-no-vapid':
    '서버에 푸시 키가 설정되지 않았어요. (서버에서 gen_vapid.py 실행 후 환경변수 설정이 필요합니다)',
};

export default function SeatsPage() {
  const [selectedFloor, setSelectedFloor] = useState(4);
  const [selectedSeatId, setSelectedSeatId] = useState(null);
  const [alerted, setAlerted] = useState(() => new Set()); // 알림을 신청한 좌석 번호: '4-01'
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState(null);

  // 자리가 나면 서버가 알림을 보내고 신청을 지우므로, 화면의 '알림 설정됨' 표시도 푼다
  const clearAlerted = useCallback((m) => {
    setAlerted((prev) => {
      if (!prev.has(m.id)) return prev;
      const next = new Set(prev);
      next.delete(m.id);
      return next;
    });
  }, []);

  const { seats, loading, error, connected } = useFloorSeats(
    selectedFloor,
    { onAvailable: clearAlerted }
  );

  // 선택한 좌석은 '번호'만 기억하고 최신 목록에서 찾아 씁니다 (실시간 변화가 상세 패널에도 반영되도록)
  const selectedSeat = seats.find((s) => s.id === selectedSeatId) ?? null;

  const handleFloorChange = (floor) => {
    setSelectedFloor(floor);
    setSelectedSeatId(null);
  };

  // 반드시 버튼을 누른 순간에 호출되어야 합니다 (브라우저가 클릭 없는 알림 권한 요청을 막음)
  const requestAlert = async (seatId) => {
    setBusy(true);
    try {
      await subscribeToAlert({ seatId });
      setAlerted((prev) => new Set(prev).add(seatId));
      setModal({
        title: '알림 신청이 완료되었습니다',
        message: '이 좌석이 비면 알림으로 알려드릴게요. 페이지를 닫아도 받을 수 있어요.',
      });
    } catch (e) {
      setModal({
        title: '알림을 신청하지 못했어요',
        message: ALERT_ERRORS[e.code] || e.message,
        error: true,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="nl-title">
        <h1>좌석 이용 현황</h1>
        <p>
          <span className={`nl-live ${connected ? '' : 'off'}`}>
            <i />
            {connected ? '실시간으로 확인 중' : '서버에 연결 중…'}
          </span>
        </p>
      </div>

      <div className="nl-seats-layout">
        <div>
          <FloorTabs selectedFloor={selectedFloor} onChange={handleFloorChange} />
          <SummaryCards seats={seats} floor={selectedFloor} />

          <div className="nl-legend" aria-label="좌석 상태 색">
            <span className="u"><i />사용 중</span>
            <span className="o"><i />점유 중</span>
            <span className="a"><i />이용 가능</span>
          </div>

          <SeatGrid
            seats={seats}
            selectedSeatId={selectedSeatId}
            onSelect={setSelectedSeatId}
            loading={loading}
            error={error}
          />
        </div>

        {/* 컴퓨터 화면에서는 오른쪽 패널, 휴대폰에서는 아래에서 올라오는 시트 */}
        <aside>
          {selectedSeat ? (
            <SeatDetail
              seat={selectedSeat}
              floor={selectedFloor}
              seatAlerted={alerted.has(selectedSeat.id)}
              busy={busy}
              onAlertSeat={() => requestAlert(selectedSeat.id)}
              onClose={() => setSelectedSeatId(null)}
            />
          ) : (
            <p className="nl-aside-empty">좌석을 선택하면 자세한 정보가 여기에 나와요.</p>
          )}
        </aside>
      </div>

      {modal && (
        <AlertModal
          title={modal.title}
          message={modal.message}
          error={modal.error}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
