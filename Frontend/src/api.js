/**
 * api.js - 서버(main.py)와 통신하는 연결 코드
 * ---------------------------------------------
 * React/순수 JS 어디서든 import 해서 쓸 수 있도록 화면과 분리해 두었습니다.
 *
 *   getFloor(floor)                  처음 화면을 그릴 때 한 층의 좌석 목록 받기   (GET /floors/4)
 *   connectSeatSocket({...})         이후 변화를 실시간으로 받기                  (WebSocket /ws)
 *   subscribeToAlert({seatId|floor}) 빈자리 알림 신청                            (POST /subscribe)
 *   getLostItems()                   수거 물품(분실물) 목록                       (GET /lost-items)
 *
 * 서버와 같은 주소에서 화면을 제공하면(기본) API_BASE 는 비워 두면 됩니다.
 * 화면 개발 서버(예: Vite 5173)를 따로 쓸 때만 window.API_BASE = "http://localhost:8000" 처럼 지정하세요.
 */

const base = () => (globalThis.window?.API_BASE ?? "");

// ---------------------------------------------------------------
// 1. 좌석 목록 (처음 로딩 / 재연결 후 동기화)
// ---------------------------------------------------------------
export async function getFloor(floor) {
  const r = await fetch(`${base()}/floors/${encodeURIComponent(floor)}`);
  if (!r.ok) {
    const err = new Error(r.status === 404 ? "등록된 좌석이 없는 층입니다" : `서버 오류 (${r.status})`);
    err.status = r.status;
    throw err;
  }
  return r.json();   // { floor: 4, seats: [{ id: '4-01', status, since, minutes }, ...], counts: {...} }
}

// ---------------------------------------------------------------
// 1-2. 수거 물품(분실물) 목록 - 관리자가 확인한 것만 내려옵니다
// ---------------------------------------------------------------
export async function getLostItems() {
  const r = await fetch(`${base()}/lost-items`);
  if (!r.ok) throw new Error(`서버 오류 (${r.status})`);
  return (await r.json()).items;   // [{ id, seat_id, floor, note, storage_place, status, registered_at, handled_at }, ...]
}

// ---------------------------------------------------------------
// 2. 실시간 변화 (WebSocket) - 끊기면 자동으로 다시 연결
// ---------------------------------------------------------------
export function connectSeatSocket({ onSeat, onStatusChange, onReconnect, retryDelay } = {}) {
  const delayFor = retryDelay ?? ((n) => Math.min(1000 * 2 ** n, 15000));   // 2초, 4초, 8초 … 최대 15초
  let ws = null, retry = 0, closed = false, timer = null;

  function url() {
    const loc = base() ? new URL(base(), globalThis.location.href) : globalThis.location;
    const proto = loc.protocol === "https:" ? "wss:" : "ws:";    // https 페이지는 wss 필수
    return `${proto}//${loc.host}/ws`;
  }

  function open() {
    ws = new WebSocket(url());
    ws.onopen = () => {
      const wasDisconnected = retry > 0;
      retry = 0;
      onStatusChange?.("open");
      // 끊긴 동안 놓친 변화가 있을 수 있으니, 다시 연결되면 화면이 목록을 새로 받도록 알려준다
      if (wasDisconnected) onReconnect?.();
    };
    ws.onmessage = (e) => {
      try {
        const m = JSON.parse(e.data);
        if (m.type === "seat") onSeat?.(m);   // { type, id: '4-01', floor: 4, status, since, minutes }
      } catch { /* 형식이 다른 메시지는 무시 */ }
    };
    ws.onclose = () => {
      onStatusChange?.("closed");
      if (closed) return;
      retry += 1;
      timer = setTimeout(open, delayFor(retry));
    };
    ws.onerror = () => ws.close();
  }

  open();
  // 아무 데이터도 없는 연결은 프록시/공유기가 끊을 수 있어 주기적으로 신호를 보낸다
  const ping = setInterval(() => { if (ws?.readyState === 1) ws.send("ping"); }, 25000);

  return {
    close() { closed = true; clearInterval(ping); clearTimeout(timer); ws?.close(); },
  };
}

// ---------------------------------------------------------------
// 3. 빈자리 알림 신청 (웹 푸시)
// ---------------------------------------------------------------
export function urlBase64ToUint8Array(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

/** 이 기기에서 푸시를 받을 수 있는지. 아이폰은 '홈 화면에 추가'한 앱으로 열어야만 가능하다. */
export function pushSupport() {
  const ua = globalThis.navigator?.userAgent ?? "";
  const isIOS = /iphone|ipad|ipod/i.test(ua);
  const standalone = globalThis.window?.matchMedia?.("(display-mode: standalone)")?.matches
                  || globalThis.navigator?.standalone === true;
  if (isIOS && !standalone) return { ok: false, reason: "ios-install" };
  if (!("serviceWorker" in globalThis.navigator) || !("PushManager" in globalThis.window))
    return { ok: false, reason: "unsupported" };
  return { ok: true };
}

const fail = (code, message) => Object.assign(new Error(message ?? code), { code });

/**
 * 반드시 '버튼 클릭' 안에서 호출해야 합니다(브라우저/iOS 가 클릭 없는 권한 요청을 막음).
 * 실패하면 err.code 로 원인을 알려줍니다:
 *   ios-install | unsupported | denied | server-no-vapid | server-error
 */
export async function subscribeToAlert({ seatId = null, floor = null } = {}) {
  const sup = pushSupport();
  if (!sup.ok) throw fail(sup.reason);

  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw fail("denied");

  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const { publicKey } = await (await fetch(`${base()}/vapid-public-key`)).json();
  if (!publicKey) throw fail("server-no-vapid");

  const key = urlBase64ToUint8Array(publicKey);
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  }

  const r = await fetch(`${base()}/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subscription: sub.toJSON(), seat_id: seatId, floor }),
  });
  if (!r.ok) throw fail("server-error", `알림 신청 실패 (${r.status})`);
  return true;
}
