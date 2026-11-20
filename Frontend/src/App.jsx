import { useEffect, useState } from 'react';
import './mobile.css';
import NavBar from './components/NavBar';
import SeatsPage from './pages/SeatsPage';
import ItemsPage from './pages/ItemsPage';
import AdminPage from './pages/AdminPage';

function App() {
  const [activePage, setActivePage] = useState('seats');

  // 관리자 화면: 주소 끝에 #admin 을 붙여 접속 (학생용 메뉴에는 나타나지 않음)
  const [isAdmin, setIsAdmin] = useState(() => window.location.hash === '#admin');
  useEffect(() => {
    const onHash = () => setIsAdmin(window.location.hash === '#admin');
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  if (isAdmin) return <AdminPage />;

  return (
    <div className="nl-app">
      <header className="nl-header">
        <div className="nl-brand">
          <div className="nl-logo" aria-hidden="true">
            <svg viewBox="0 0 48 48" width="22" height="22">
              <path d="M24 23 C18 16 19 7 24 5 C29 7 30 16 24 23Z" fill="white" />
              <path d="M25 24 C32 18 41 19 43 24 C41 29 32 30 25 24Z" fill="white" />
              <path d="M24 25 C30 32 29 41 24 43 C19 41 18 32 24 25Z" fill="white" />
              <path d="M23 24 C16 30 7 29 5 24 C7 19 16 18 23 24Z" fill="white" />
              <circle cx="24" cy="24" r="3" fill="#2f62e0" />
            </svg>
          </div>
          <div>
            <strong>나리도서관</strong>
          </div>
        </div>
        <NavBar activePage={activePage} onChange={setActivePage} />
      </header>

      <main className="nl-main">
        {/* 좌석 화면은 메뉴를 옮겨 다녀도 실시간 연결과 알림 신청 표시가 유지되도록 숨기기만 한다 */}
        <div hidden={activePage !== 'seats'}>
          <SeatsPage />
        </div>

        {/* 수거 물품 화면은 열 때마다 서버에서 새로 불러온다 */}
        {activePage === 'items' && <ItemsPage />}

      </main>
    </div>
  );
}

export default App;
