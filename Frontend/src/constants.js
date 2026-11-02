// 서버(main.py / db.py)가 보내는 좌석 상태 값과 똑같은 이름입니다. 변환 없이 그대로 씁니다.
//   available = 빈 자리 / inUse = 사용 중 / occupied = 점유 중(사람은 없고 물품만 있음)
export const STATUS_LABELS = {
  available: '이용 가능',
  inUse: '사용 중',
  occupied: '점유 중',
};

// 층은 숫자(4, 5, 6), 좌석 번호는 '4-01' 형식이며 서버와 화면이 똑같이 씁니다 (변환 없음).
export const FLOORS = [4, 5, 6];
