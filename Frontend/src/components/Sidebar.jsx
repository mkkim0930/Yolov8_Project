export default function Sidebar({ activePage, onChange }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">
          <svg
            viewBox="0 0 48 48"
            width="29"
            height="29"
            aria-label="개나리 꽃잎 로고"
            role="img"
          >
            <path
              d="M24 23 C18 16 19 7 24 5 C29 7 30 16 24 23Z"
              fill="white"
            />
            <path
              d="M25 24 C32 18 41 19 43 24 C41 29 32 30 25 24Z"
              fill="white"
            />
            <path
              d="M24 25 C30 32 29 41 24 43 C19 41 18 32 24 25Z"
              fill="white"
            />
            <path
              d="M23 24 C16 30 7 29 5 24 C7 19 16 18 23 24Z"
              fill="white"
            />
            <circle cx="24" cy="24" r="3" fill="#3467df" />
          </svg>
        </div>

        <div>
          <h2>나리도서관</h2>
          <p>HYWU Library</p>
        </div>
      </div>

      <div className="sidebar-section-title">MENU</div>

      <nav className="sidebar-menu">
        <button
          className={activePage === 'seats' ? 'active' : ''}
          onClick={() => onChange('seats')}
        >
          <span className="menu-icon">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="5" y="3" width="14" height="5" rx="1" />
              <path d="M3 11h18M5 11v9M19 11v9" />
              <path d="M8 16h8M9 16v4M15 16v4" />
            </svg>
          </span>
          좌석 이용 현황
        </button>

        <button
          className={activePage === 'items' ? 'active' : ''}
          onClick={() => onChange('items')}
        >
          <span className="menu-icon">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="4" y="8" width="16" height="13" rx="2" />
              <path d="M9 8V6a3 3 0 0 1 6 0v2" />
              <path d="M4 13h16" />
              <path d="M11 13v2h2v-2" />
            </svg>
          </span>
          수거 물품 안내
        </button>
      </nav>

      <div className="sidebar-footer">한양여자대학교</div>
    </aside>
  );
}
