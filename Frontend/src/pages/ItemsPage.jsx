import { useCallback, useEffect, useState } from 'react';
import { getLostItems } from '../api';
import { formatDateTime } from '../utils/time';

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
    <div>
      <div className="nl-title">
        <h1>수거 물품 안내</h1>
        <p>관리자가 확인 후 보관 중인 물품 목록이에요<br />주인이라면 보관 장소로 와 주세요</p>
      </div>

      {loading && <p className="nl-message">수거 물품을 불러오는 중입니다…</p>}

      {!loading && error && (
        <div className="nl-empty">
          <h3>불러오지 못했어요</h3>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="nl-empty">
          <h3>보관 중인 수거 물품이 없습니다</h3>
          <p>자리를 오래 비운 좌석의 물품은<br />관리자가 확인한 뒤 이곳에 표시됩니다</p>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="nl-items">
          {items.map((item) => (
            <article key={item.id} className="nl-item">
              <div className="nl-item-top">
                <strong>{item.seat_id}번 좌석</strong>
                <span className="nl-badge">보관 중</span>
              </div>
              {item.note && <p className="nl-item-note">{item.note}</p>}
              <p className="nl-item-meta">{formatDateTime(item.handled_at || item.registered_at)} 수거</p>
              {item.storage_place && (
                <p className="nl-item-meta">보관 장소 · <b>{item.storage_place}</b></p>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
