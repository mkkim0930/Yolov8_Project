# 서버 API (프론트엔드 nari-library-share-update 기준)

좌석 번호는 `4-01`(층-번호), 층은 숫자, 상태는 `available`(빈 자리) / `inUse`(사용 중) / `occupied`(점유 중).

| 누가 | 요청 | 설명 |
|---|---|---|
| 탐지 | `POST /seat-status` `{"seat_id":"4-01","status":"inUse"}` | 헤더 `X-Detector-Key`(서버에 DETECTOR_KEY 설정 시). 404=없는 좌석, 401=키 불일치, 422=상태 이름 틀림 |
| 화면 | `GET /floors/4` | `{floor:4, seats:[{id,status,since,minutes}], counts:{total,available,inUse,occupied}}` (좌석 번호순) |
| 화면 | `WS /ws` | 변화 때마다 `{type:"seat", id:"4-01", floor:4, status, since, minutes:0}` |
| 화면 | `GET /vapid-public-key` | `{publicKey}` |
| 화면 | `POST /subscribe` | `{subscription, seat_id:"4-01"}` 또는 `{subscription, floor:4}`. 알림은 1회용 |
| 화면 | `GET /lost-items` | `{items:[{id,seat_id,floor,note,storage_place,status:"STORED",registered_at,handled_at}]}` (관리자 확인된 것만) |
| 관리자 | `GET /admin/lost-items?status=PENDING\|STORED\|CLAIMED\|ALL` | 헤더 `X-Admin-Token` |
| 관리자 | `POST /admin/lost-items/{id}/confirm` | 본문(선택) `{note, storage_place}`. PENDING→STORED |
| 관리자 | `POST /admin/lost-items/{id}/claimed` | STORED→CLAIMED |
| 관리자 | `WS /ws/admin?token=...` | 사석화 발생 시 `{type:"sakhwa", id, floor, since, item_id}` |
| 공통 | `GET /health` | `{ok:true}` |

## DB (library.db, SQLite)
- `seats(seat_id, floor, status, status_since, updated_at)` — 기본 상태 `available`
- `seat_events` — 상태가 바뀐 기록
- `push_subscriptions(endpoint, p256dh, auth, seat_id, floor, target, active)` — target 은 `seat:4-01` / `floor:4`
- `lost_items(id, seat_id, floor, image_path, note, storage_place, status, registered_at, handled_at, claimed_at)`

예전 구조의 library.db 가 있으면 서버/`setup_db.py` 가 `library.db.bak-날짜` 로 백업하고 새로 만듭니다.
