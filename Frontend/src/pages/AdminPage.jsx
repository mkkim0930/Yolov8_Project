import { useCallback, useEffect, useState } from 'react';
import '../admin.css';
import { formatDateTime, formatMinutes, minutesSince } from '../utils/time';

// ------------------------------------------------------------------
// 관리자 화면: 주소 끝에 #admin 을 붙여서 접속합니다 (예: http://localhost:5173/#admin)
// 학생용 메뉴에는 나타나지 않으며, 관리자 토큰(서버의 ADMIN_TOKEN)을 입력해야 동작합니다.
// 서버 API: GET /admin/lost-items, POST /admin/lost-items/{id}/confirm|claimed, WebSocket /ws/admin
// ------------------------------------------------------------------

const base = () => globalThis.window?.API_BASE ?? '';
const TOKEN_KEY = 'nari-admin-token';

// 토큰은 이 탭이 열려 있는 동안만 기억합니다 (탭을 닫으면 사라짐)
const readToken = () => {
  try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
};
const saveToken = (token) => {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* 저장이 막힌 환경이면 새로고침 때 다시 입력하면 됩니다 */ }
};

async function adminFetch(path, token, options = {}) {
  const r = await fetch(`${base()}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token },
  });
  if (r.status === 401) {
    let detail = '';
    try { detail = (await r.json()).detail; } catch { /* 본문이 없으면 기본 문구 */ }
    throw Object.assign(new Error(detail || '관리자 토큰이 올바르지 않아요'), { status: 401 });
  }
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json()).detail; } catch { /* 본문이 없으면 코드만 보여 줌 */ }
    throw new Error(detail || `서버 오류 (${r.status})`);
  }
  return r.json();
}

const fetchAllItems = (token) =>
  adminFetch('/admin/lost-items?status=ALL', token).then((d) => d.items);

// 서버의 /ws/admin 에 연결해 사석화 알림을 받는다. 끊기면 다시 연결.
function connectAdminSocket(token, { onSakhwa, onStatusChange }) {
  let ws = null, closed = false, retry = 0, timer = null;

  const url = () => {
    const loc = base() ? new URL(base(), globalThis.location.href) : globalThis.location;
    const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${loc.host}/ws/admin?token=${encodeURIComponent(token)}`;
  };

  const open = () => {
    ws = new WebSocket(url());
    ws.onopen = () => { retry = 0; onStatusChange('open'); };
    ws.onmessage = (e) => {
      try {
        const m = JSON.parse(e.data);
        if (m.type === 'sakhwa') onSakhwa(m);
      } catch { /* 형식이 다른 메시지는 무시 */ }
    };
    ws.onclose = () => {
      onStatusChange('closed');
      if (closed) return;
      retry += 1;
      timer = setTimeout(open, Math.min(1000 * 2 ** retry, 15000));
    };
    ws.onerror = () => ws.close();
  };

  open();
  const ping = setInterval(() => { if (ws?.readyState === 1) ws.send('ping'); }, 25000);
  return {
    close() {
      closed = true;
      clearInterval(ping);
      clearTimeout(timer);
      ws?.close();
    },
  };
}

// ---- 로그인 ----
function LoginForm({ onLogin }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!value.trim()) return;
    setBusy(true);
    setError('');
    try {
      await fetchAllItems(value.trim());     // 토큰이 맞는지 확인
      onLogin(value.trim());
    } catch (err) {
      setError(err.status === 401 ? err.message : `서버에 연결하지 못했어요 (${err.message})`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="adm-login" onSubmit={submit}>
      <h2>관리자 로그인</h2>
      <p>서버를 켤 때 설정한 관리자 토큰(ADMIN_TOKEN)을 입력하세요.</p>
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="관리자 토큰"
        autoFocus
      />
      {error && <p className="adm-error">{error}</p>}
      <button className="adm-btn primary" disabled={busy || !value.trim()}>
        {busy ? '확인 중…' : '로그인'}
      </button>
    </form>
  );
}

// ---- 확인 대기 카드 (설명과 보관 장소를 적고 학생에게 공개) ----
function PendingCard({ item, onConfirm, busy, now }) {
  const [note, setNote] = useState('');
  const [place, setPlace] = useState('');

  return (
    <div className="adm-card">
      <div className="adm-card-head">
        <strong>{item.floor}층 {item.seat_id}</strong>
        <span className="adm-badge wait">확인 대기</span>
      </div>
      <p className="adm-meta">
        사석화 감지 {formatDateTime(item.registered_at)} ·{' '}
        {formatMinutes(minutesSince(item.registered_at, now))} 전
      </p>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="물품 설명 (예: 검정 백팩)"
        maxLength={100}
      />
      <input
        value={place}
        onChange={(e) => setPlace(e.target.value)}
        placeholder="보관 장소 (예: 1층 안내데스크)"
        maxLength={100}
      />
      <button
        className="adm-btn primary"
        disabled={busy}
        onClick={() => onConfirm(item.id, note.trim(), place.trim())}
      >
        확인하고 학생에게 공개
      </button>
    </div>
  );
}

// ---- 관리자 화면 본체 ----
function AdminBoard({ token, onLogout }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [banner, setBanner] = useState(null);
  const [connected, setConnected] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(() => {
    return fetchAllItems(token)
      .then((list) => { setItems(list); setError(''); })
      .catch((e) => {
        if (e.status === 401) onLogout();     // 토큰이 바뀌었으면 다시 로그인
        else setError(e.message);
      });
  }, [token, onLogout]);

  // 처음 불러오기 + 10초마다 갱신(실시간 알림을 놓쳐도 맞춰지도록)
  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  // 경과 시간 표시가 멈춰 보이지 않도록 30초마다 현재 시각 갱신
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  // 사석화가 감지되면 바로 알려 준다
  useEffect(() => {
    const socket = connectAdminSocket(token, {
      onSakhwa: (m) => { setBanner(m); load(); },
      onStatusChange: (st) => setConnected(st === 'open'),
    });
    return () => socket.close();
  }, [token, load]);

  const act = async (id, path, body) => {
    setBusyId(id);
    try {
      await adminFetch(path, token, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
      setError('');
      await load();
    } catch (e) {
      if (e.status === 401) onLogout();
      else setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  const byNewest = (a, b) => String(b.registered_at).localeCompare(String(a.registered_at));
  const pending = items.filter((i) => i.status === 'PENDING').sort(byNewest);
  const stored = items.filter((i) => i.status === 'STORED').sort(byNewest);
  const claimedCount = items.filter((i) => i.status === 'CLAIMED').length;

  return (
    <>
      <div className="adm-status">
        <span className={`adm-dot ${connected ? 'on' : ''}`} />
        {connected ? '실시간 연결됨' : '서버에 연결 중…'}
      </div>

      {banner && (
        <div className="adm-banner" role="alert">
          <span>
            <strong>사석화 감지</strong> · {banner.floor}층 {banner.id} 좌석의 물품이 오래 놓여 있어요.
            아래 확인 대기 목록에서 확인해 주세요.
          </span>
          <button className="adm-link" onClick={() => setBanner(null)}>닫기</button>
        </div>
      )}

      {error && <p className="adm-error">{error}</p>}

      <section className="adm-section">
        <h3>확인 대기 <em>{pending.length}</em></h3>
        {pending.length === 0 ? (
          <p className="adm-empty">확인할 분실물이 없어요.</p>
        ) : (
          <div className="adm-grid">
            {pending.map((item) => (
              <PendingCard
                key={item.id}
                item={item}
                now={now}
                busy={busyId === item.id}
                onConfirm={(id, note, place) =>
                  act(id, `/admin/lost-items/${id}/confirm`, { note, storage_place: place })
                }
              />
            ))}
          </div>
        )}
      </section>

      <section className="adm-section">
        <h3>보관 중 <em>{stored.length}</em></h3>
        {stored.length === 0 ? (
          <p className="adm-empty">보관 중인 물품이 없어요.</p>
        ) : (
          <div className="adm-grid">
            {stored.map((item) => (
              <div className="adm-card" key={item.id}>
                <div className="adm-card-head">
                  <strong>{item.floor}층 {item.seat_id}</strong>
                  <span className="adm-badge ok">보관 중</span>
                </div>
                <p className="adm-meta">
                  {item.note || '설명 없음'}
                  {item.storage_place && ` · ${item.storage_place}`}
                </p>
                <p className="adm-meta">확인 {formatDateTime(item.handled_at || item.registered_at)}</p>
                <button
                  className="adm-btn"
                  disabled={busyId === item.id}
                  onClick={() => act(item.id, `/admin/lost-items/${item.id}/claimed`)}
                >
                  수령 완료 (주인이 찾아감)
                </button>
              </div>
            ))}
          </div>
        )}
        {claimedCount > 0 && <p className="adm-empty">수령 완료 {claimedCount}건</p>}
      </section>
    </>
  );
}

export default function AdminPage() {
  const [token, setToken] = useState(readToken);

  const login = (t) => { saveToken(t); setToken(t); };
  const logout = useCallback(() => { saveToken(''); setToken(''); }, []);

  return (
    <div className="adm-wrap">
      <header className="adm-header">
        <div>
          <p className="adm-sub">ADMIN</p>
          <h1>분실물 관리</h1>
        </div>
        <div className="adm-header-actions">
          <a className="adm-link" href="#" onClick={() => { window.location.hash = ''; }}>
            학생 화면으로
          </a>
          {token && <button className="adm-link" onClick={logout}>로그아웃</button>}
        </div>
      </header>

      {token ? <AdminBoard token={token} onLogout={logout} /> : <LoginForm onLogin={login} />}
    </div>
  );
}
