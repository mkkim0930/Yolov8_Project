// 모바일: 화면 아래 탭 / 넓은 화면: 위쪽 탭 (모양은 mobile.css 가 결정)
const SeatIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="5" y="3" width="14" height="5" rx="1" />
    <path d="M3 11h18M5 11v9M19 11v9" />
    <path d="M8 16h8M9 16v4M15 16v4" />
  </svg>
);
const BoxIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="8" width="16" height="13" rx="2" />
    <path d="M9 8V6a3 3 0 0 1 6 0v2" />
    <path d="M4 13h16" />
  </svg>
);

export default function NavBar({ activePage, onChange }) {
  return (
    <nav className="nl-nav" aria-label="메뉴">
      <button className={activePage === 'seats' ? 'active' : ''} onClick={() => onChange('seats')}>
        <span className="ic"><SeatIcon /></span>좌석 현황
      </button>
      <button className={activePage === 'items' ? 'active' : ''} onClick={() => onChange('items')}>
        <span className="ic"><BoxIcon /></span>수거 물품
      </button>
    </nav>
  );
}
