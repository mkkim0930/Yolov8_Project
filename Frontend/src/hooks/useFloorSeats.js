import { useCallback, useEffect, useRef, useState } from 'react';
import { getFloor, connectSeatSocket } from '../api';
import { minutesSince } from '../utils/time';

/**
 * 한 층의 좌석 목록을 서버에서 받아오고, 실시간으로 바뀌는 상태를 반영합니다.
 *
 *   const { seats, loading, error, connected } = useFloorSeats(4, { onAvailable });
 *
 * seats    : [{ id: '4-01', status: 'available' | 'inUse' | 'occupied', since, minutes: 35 }, ...]
 * onAvailable(m) : (선택) 어느 층이든 좌석이 빈 자리가 되면 호출됩니다 (알림 신청 표시를 풀 때 사용)
 */
export default function useFloorSeats(floor, { onAvailable } = {}) {
  const [seats, setSeats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  // WebSocket 은 한 번만 열어 두고, 최신 층/콜백은 ref 로 읽습니다 (층을 바꿀 때마다 다시 연결하지 않기 위해)
  const floorRef = useRef(floor);
  const availableRef = useRef(onAvailable);
  useEffect(() => {
    floorRef.current = floor;
    availableRef.current = onAvailable;
  });

  const load = useCallback(() => {
    const target = floorRef.current;
    return getFloor(target)
      .then((data) => {
        if (floorRef.current !== target) return;   // 그 사이 다른 층으로 바뀌었으면 버림
        setSeats(data.seats);
        setError('');
      })
      .catch((e) => {
        if (floorRef.current !== target) return;
        setSeats([]);
        setError(e.message);
      })
      .finally(() => {
        if (floorRef.current === target) setLoading(false);
      });
  }, []);

  // 층이 바뀌면 목록을 새로 받는다
  useEffect(() => {
    setLoading(true);
    load();
  }, [floor, load]);

  // 실시간 변화: 해당 좌석만 갱신
  useEffect(() => {
    const socket = connectSeatSocket({
      onSeat: (m) => {
        if (m.status === 'available') availableRef.current?.(m);
        if (m.floor !== floorRef.current) return;
        setSeats((prev) =>
          prev.map((s) =>
            s.id === m.id ? { ...s, status: m.status, since: m.since, minutes: 0 } : s
          )
        );
      },
      onStatusChange: (st) => setConnected(st === 'open'),
      onReconnect: load,   // 연결이 끊겼다 돌아오면 놓친 변화가 없도록 목록을 새로 받는다
    });
    return () => socket.close();
  }, [load]);

  // 경과 시간이 멈춰 보이지 않도록 30초마다 현재 시각을 갱신
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  // 시작 시각(since)으로 계산하고, 읽을 수 없는 값이면 서버가 계산해 준 minutes 를 씁니다
  const withMinutes = seats.map((s) => ({
    ...s,
    minutes: Number.isNaN(Date.parse(s.since)) ? (s.minutes ?? 0) : minutesSince(s.since, now),
  }));

  return { seats: withMinutes, loading, error, connected };
}
