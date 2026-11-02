
import { useState } from 'react';
import './SeatMap.css';

// 임시 좌석 데이터
const floorData = {
  4: [
    { id: '4-01', status: 'available' },
    { id: '4-02', status: 'occupied' },
    { id: '4-03', status: 'available' },
    { id: '4-04', status: 'available' },
  ],
  5: [
    { id: '5-01', status: 'occupied' },
    { id: '5-02', status: 'available' },
    { id: '5-03', status: 'occupied' },
    { id: '5-04', status: 'available' },
    { id: '5-05', status: 'available' },
  ],
  6: [
    { id: '6-01', status: 'available' },
    { id: '6-02', status: 'occupied' },
    { id: '6-03', status: 'available' },
    { id: '6-04', status: 'occupied' },
  ],
};

function SeatMap({ floor = 4 }) {
  const [selectedSeatId, setSelectedSeatId] = useState(null);

  const seats = floorData[floor] ?? [];
  const selectedSeat = seats.find(
    (seat) => seat.id === selectedSeatId
  );

  return (
    <div className="library-map">
      <div className="map-heading">
        <h3>{floor}층 좌석 배치도</h3>
      </div>

      <div className="floor-map">
        {/* 왼쪽 벽을 따라 배치된 좌석 */}
        <div className="seat-area">
          <div className="seat-wall">
            {seats.map((seat) => (
              <button
                key={seat.id}
                type="button"
                className={`map-seat ${seat.status} ${
                  selectedSeatId === seat.id
                    ? 'selected'
                    : ''
                }`}
                onClick={() => setSelectedSeatId(seat.id)}
                aria-pressed={selectedSeatId === seat.id}
                aria-label={`${seat.id}번 좌석 ${
                  seat.status === 'occupied'
                    ? '점유 중'
                    : '이용 가능'
                }`}
              >
                <span className="map-seat-number">
                  {seat.id}
                </span>
                <span className="map-seat-status">
                  {seat.status === 'occupied'
                    ? '점유 중'
                    : '이용 가능'}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* 좌석 구역으로 이어지는 복도 */}
        <div className="map-corridor">
          <span className="corridor-direction">
            ← 1인석
          </span>
          <span className="corridor-label">복도</span>
        </div>

        {/* 복도와 연결된 중앙계단 */}
        <div className="stairs-row">
          <div className="central-stairs">
            <div className="stair-steps">
              {Array.from({ length: 7 }).map(
                (_, index) => (
                  <span key={index} />
                )
              )}
            </div>
            <strong>중앙계단</strong>
          </div>
        </div>
      </div>

      {/* 좌석 상태 */}
      <div className="map-legend">
        <span>
          <i className="map-legend-dot available-dot" />
          이용 가능
        </span>
        <span>
          <i className="map-legend-dot occupied-dot" />
          점유 중
        </span>
      </div>

      {/* 선택한 좌석 정보 */}
      {selectedSeat && (
        <div className="map-seat-detail">
          <div>
            <strong>{selectedSeat.id}번 좌석</strong>
            <p
              className={
                selectedSeat.status === 'occupied'
                  ? 'detail-occupied'
                  : 'detail-available'
              }
            >
              {selectedSeat.status === 'occupied'
                ? '점유 중'
                : '이용 가능'}
            </p>
          </div>

          <button
            type="button"
            onClick={() => setSelectedSeatId(null)}
          >
            닫기
          </button>
        </div>
      )}
    </div>
  );
}

export default SeatMap;
