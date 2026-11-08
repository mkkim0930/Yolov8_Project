import { useEffect, useState } from 'react';
import './App.css';
import './extra.css';
import Sidebar from './components/Sidebar';
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
    <div className="app-container">
      <Sidebar activePage={activePage} onChange={setActivePage} />

      <main className="main-content">
        <header className="top-header">
          <div className="header-location">
            나리도서관 <span>/</span> 이용 안내
          </div>
        </header>

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
