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


## (추가) AI 가 감지한 물품 자동 등록

`POST /seat-status` 에 선택 항목 2개가 생겼습니다 (없어도 예전처럼 동작).

| 항목 | 설명 |
|---|---|
| `items` | 점유 중일 때 AI 가 본 물품 클래스 이름 목록. 예: `["book","book","laptop"]` |
| `image` | 좌석 영역을 잘라 만든 JPEG 사진을 base64 로 인코딩한 문자열 (700KB 이하) |

- 서버는 점유 중인 좌석의 최신 물품/사진을 기억해 두었다가, 사석화(점유 중 기준 시간 초과)가 확정되면
  분실물(PENDING)을 만들면서 `note`("책 2개, 노트북 (AI 자동 감지)")와 사진을 자동으로 채웁니다.
- 점유가 풀리면(사용 중/빈 자리) 기억한 사진은 지워집니다. 주인이 찾아가면(claimed) 사진도 지워집니다.
- 분실물 목록 응답(`/lost-items`, `/admin/lost-items`)에 `image_url` 이 추가됩니다. 사진이 없으면 `null`.
- `GET /lost-items/image/{파일이름}.jpg` : 사진. 파일 이름이 추측하기 어려운 값입니다.
- 관리자가 `confirm` 할 때 `note` 를 비워 보내면 AI 가 적은 설명이 그대로 유지됩니다.
