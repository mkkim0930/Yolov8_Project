/**
 * sw.js - Service Worker
 * 웹페이지를 닫아도, 브라우저를 꺼도 서버가 보낸 푸시를 받아 알림창을 띄웁니다.
 * 서버(main.py)가 보내는 내용: { title, body, seat_id, floor }
 */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; }
  catch { data = { body: event.data ? event.data.text() : "" }; }

  event.waitUntil(
    self.registration.showNotification(data.title || "빈자리 알림", {
      body: data.body || "",
      tag: data.seat_id || "seat",        // 같은 좌석 알림이 겹치면 하나로 합침
      data: { floor: data.floor, seat_id: data.seat_id },
    })
  );
});

// 알림을 누르면 열려 있는 탭으로 이동, 없으면 새로 연다
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) if ("focus" in c) return c.focus();
      return self.clients.openWindow("/");
    })
  );
});
