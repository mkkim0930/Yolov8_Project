// 상태별 좌석 아이콘 (색은 아이콘 안에 들어 있음: 파랑=이용 가능, 초록=사용 중, 주황=점유 중)
const COMMON = { viewBox: '0 0 64 64', fill: 'none', strokeWidth: 3.2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };
const DESK = (
  <>
    <path d="M14 30V15a3 3 0 0 1 3-3H47a3 3 0 0 1 3 3V30" />
    <path d="M8 38H56" />
    <path d="M14 38V54" />
    <path d="M50 38V54" />
  </>
);

export default function SeatIcon({ status }) {
  if (status === 'inUse') {
    return (
      <svg {...COMMON} stroke="#22A55B">
        {DESK}
        <circle cx="32" cy="23" r="6" />
        <path d="M20 38a12 9 0 0 1 24 0" />
      </svg>
    );
  }
  if (status === 'occupied') {
    return (
      <svg {...COMMON} stroke="#F97316">
        {DESK}
        <path d="M21 38V30a6 6 0 0 1 6-6h10a6 6 0 0 1 6 6V38" />
        <path d="M25 38v-6h14v6" />
        <path d="M29 24v-2a3 3 0 0 1 6 0v2" />
      </svg>
    );
  }
  return (
    <svg {...COMMON} stroke="#3B82F6">
      {DESK}
      <path d="M25 24l5 5l10-10" />
    </svg>
  );
}
