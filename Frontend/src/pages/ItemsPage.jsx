import { useCallback, useEffect, useState } from 'react';
import { getLostItems } from '../api';
import { formatDateTime } from '../utils/time';

const BoxIcon = ({ size }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="4" y="8" width="16" height="13" rx="2" />
    <path d="M9 8V6a3 3 0 0 1 6 0v2" />
    <path d="M4 13h16" />
    <path d="M11 13v2h2v-2" />
  </svg>
);

export default function ItemsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    return getLostItems()
      .then((list) => {
        setItems(list);
        setError('');
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // 이 페이지를 열 때마다 새로 불러오고, 열어 둔 동안은 30초마다 갱신
  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div className="page-content">
      <div className="page-title">
        <div>
          <p className="page-subtitle">COLLECTED ITEMS</p>
          <h1>수거 물품 안내</h1>
          <p className="page-description">
            도서관에서 수거되어 보관 중인 물품을 확인하는 페이지입니다.
          </p>
        </div>
      </div>

      {loading && (
        <div className="empty-page">
          <p>수거 물품을 불러오는 중입니다…</p>
        </div>
      )}

      {!loading && error && (
        <div className="empty-page">
          <h3>불러오지 못했어요</h3>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="empty-page">
          <div className="empty-icon">
            <BoxIcon size={40} />
          </div>
          <h3>보관 중인 수거 물품이 없습니다</h3>
          <p>점유가 오래 이어진 좌석의 물품은 관리자 확인 후 이곳에 표시됩니다.</p>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="item-grid">
          {items.map((item) => (
            <div key={item.id} className="item-card">
              <div className="item-thumb">
                <BoxIcon size={32} />
              </div>
              <div className="item-info">
                <strong>{item.seat_id}번 좌석에서 수거</strong>
                {item.note && <p>{item.note}</p>}
                <p>
                  수거 시각 {formatDateTime(item.handled_at || item.registered_at)}
                  {item.storage_place && ` · 보관 장소 ${item.storage_place}`}
                </p>
              </div>
              <span className="item-badge">보관 중</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
