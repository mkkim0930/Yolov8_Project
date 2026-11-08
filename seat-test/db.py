"""
db.py  -  좌석 서비스용 DB 모듈 (SQLite)
=========================================

프론트엔드(nari-library-share)가 쓰는 데이터 모양에 그대로 맞춘 구조입니다.
  층      : 숫자 4 / 5 / 6
  좌석 번호: '4-01' (층-번호)
  상태    : available(빈 자리) / inUse(사용 중) / occupied(점유 중: 사람은 없고 물품만 있음)
  경과    : 상태가 시작된 시각(since)에서 계산한 분(minutes)

테이블 4개
----------
seats              좌석의 '현재' 상태 + 그 상태가 시작된 시각  (사석화 1시간 판정의 핵심)
seat_events        상태가 바뀐 기록(이력)                    (통계 / 오탐지 검증용)
push_subscriptions 빈자리 알림 신청 (웹 푸시 구독 정보)
lost_items         사석화로 등록된 분실물 (수거 물품 안내 화면)

시각은 '2026-10-31T18:12:05+09:00' 처럼 시간대를 포함해 저장합니다 (브라우저가 어디서 열어도 같은 시각으로 읽도록).

예전 구조의 library.db 가 있으면 init_db() 가 자동으로 백업 파일로 옮기고 새로 만듭니다 (데이터를 지우지 않음).
"""

import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = "library.db"
SCHEMA_VERSION = 2

AVAILABLE, IN_USE, OCCUPIED = "available", "inUse", "occupied"   # 빈 자리 / 사용 중 / 점유 중
VALID_STATUS = (AVAILABLE, IN_USE, OCCUPIED)
SAKHWA_THRESHOLD = timedelta(hours=1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS seats (
    seat_id       TEXT PRIMARY KEY,           -- 예: 4-01
    floor         INTEGER NOT NULL,           -- 4, 5, 6
    status        TEXT NOT NULL DEFAULT 'available',   -- available / inUse / occupied
    status_since  TEXT NOT NULL,              -- 현재 상태가 시작된 시각
    updated_at    TEXT NOT NULL               -- 마지막으로 탐지 결과를 받은 시각
);

CREATE TABLE IF NOT EXISTS seat_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seat_id     TEXT NOT NULL,
    old_status  TEXT,
    new_status  TEXT NOT NULL,
    at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint    TEXT NOT NULL,                -- 브라우저가 만든 구독 주소
    p256dh      TEXT NOT NULL,                -- 구독 암호화 키
    auth        TEXT NOT NULL,                -- 구독 인증 키
    seat_id     TEXT,                         -- 특정 좌석 알림 (없으면 NULL)
    floor       INTEGER,                      -- 층 단위 알림   (없으면 NULL)
    target      TEXT NOT NULL,                -- 'seat:4-01' 또는 'floor:4'
    active      INTEGER NOT NULL DEFAULT 1,   -- 1: 대기 중, 0: 이미 발송됨
    created_at  TEXT NOT NULL,
    UNIQUE(endpoint, target)                  -- 한 브라우저가 여러 좌석/층을 동시에 신청할 수 있다
);

CREATE TABLE IF NOT EXISTS lost_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    seat_id       TEXT NOT NULL,              -- 어느 좌석에서 나왔는지
    floor         INTEGER NOT NULL,
    image_path    TEXT,                       -- 캡처한 사진 파일 경로 (아직 저장 기능 없음)
    note          TEXT,                       -- 관리자 메모 (예: 검정 백팩)
    storage_place TEXT,                       -- 보관 장소 (예: 1층 안내데스크)
    status        TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING(관리자 확인 대기) / STORED(보관, 학생에게 공개) / CLAIMED(수령 완료)
    registered_at TEXT NOT NULL,              -- 사석화로 등록된 시각
    handled_at    TEXT,                       -- 관리자가 확인한 시각
    claimed_at    TEXT                        -- 주인이 찾아간 시각
);

CREATE INDEX IF NOT EXISTS idx_events_seat ON seat_events(seat_id, at);
CREATE INDEX IF NOT EXISTS idx_sub_active  ON push_subscriptions(active);
CREATE INDEX IF NOT EXISTS idx_seats_floor ON seats(floor);
"""

SEAT_ORDER = "ORDER BY CAST(substr(seat_id, instr(seat_id, '-') + 1) AS INTEGER), seat_id"   # 4-2 가 4-10 보다 앞


# ------------------------------------------------------------------
# 시간
# ------------------------------------------------------------------
def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_time(ts):
    """저장된 시각 문자열 -> 시간대가 있는 datetime (시간대가 없는 값은 이 컴퓨터의 현지 시각으로 본다)."""
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.astimezone()


def minutes_since(ts, now=None):
    """ts 부터 지금(now)까지 몇 분 지났는지. now 는 문자열/datetime/None."""
    if now is None:
        now_dt = datetime.now().astimezone()
    elif isinstance(now, str):
        now_dt = parse_time(now)
    else:
        now_dt = now if now.tzinfo else now.astimezone()
    return max(0, int((now_dt - parse_time(ts)).total_seconds() // 60))


# ------------------------------------------------------------------
# 연결 / 초기화
# ------------------------------------------------------------------
@contextmanager
def get_conn(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # 읽기/쓰기 동시 접근에 유리
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def backup_db(path):
    """DB 파일을 지우지 않고 '이름.bak-날짜시각' 으로 옮긴다. 옮긴 새 이름을 반환 (파일이 없으면 None)."""
    if not os.path.exists(path):
        return None
    backup = f"{path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.move(path, backup)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            shutil.move(path + suffix, backup + suffix)
    return backup


def _is_old_db(path):
    """표(table)가 이미 있는데 새 구조 표시(user_version)가 없는 DB = 예전 구조."""
    if not os.path.exists(path):
        return False
    c = sqlite3.connect(path)
    try:
        version = c.execute("PRAGMA user_version").fetchone()[0]
        tables = c.execute("SELECT count(*) FROM sqlite_master "
                           "WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    finally:
        c.close()
    return tables > 0 and version < SCHEMA_VERSION


def init_db(path=None):
    path = path or DB_PATH
    if _is_old_db(path):
        backup = backup_db(path)
        print(f"[db] 예전 구조의 DB 를 {backup} 로 백업하고 새로 만들었습니다. "
              f"좌석은 'python setup_db.py --demo' 등으로 다시 등록하세요.")
    with get_conn(path) as c:
        c.executescript(SCHEMA)
        c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# ------------------------------------------------------------------
# 좌석
# ------------------------------------------------------------------
def upsert_seats(floor, seats, path=None, now=None):
    """좌석을 등록한다 (처음엔 available). 이미 있으면 건드리지 않음.
    seats: 좌석 번호 목록 또는 {좌석번호: 좌표} dict.  좌석 번호는 '<층>-<번호>' 형식이어야 한다 (예: 4층 -> 4-01)."""
    floor = int(floor)
    ids = list(seats)
    bad = [s for s in ids if not str(s).startswith(f"{floor}-")]
    if bad:
        raise ValueError(f"{floor}층 좌석 번호는 '{floor}-01' 형식이어야 합니다: {bad}")
    now = now or _now()
    with get_conn(path) as c:
        for sid in ids:
            c.execute("INSERT OR IGNORE INTO seats(seat_id, floor, status, status_since, updated_at) "
                      "VALUES (?, ?, ?, ?, ?)", (sid, floor, AVAILABLE, now, now))


def update_seat_status(seat_id, new_status, path=None, now=None):
    """탐지 결과를 반영한다.
    - 상태가 '바뀌었으면' status_since 를 지금으로 리셋 (타이머 재시작)
    - 상태가 '같으면' status_since 는 그대로 둔다 (시간이 계속 누적됨)
    반환: {"changed", "old", "new", "became_empty"}
    """
    if new_status not in VALID_STATUS:
        raise ValueError(f"unknown status: {new_status}")
    now = now or _now()
    with get_conn(path) as c:
        row = c.execute("SELECT status FROM seats WHERE seat_id=?", (seat_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown seat: {seat_id}")
        old = row["status"]
        if old == new_status:
            c.execute("UPDATE seats SET updated_at=? WHERE seat_id=?", (now, seat_id))
            return {"changed": False, "old": old, "new": new_status, "became_empty": False}
        c.execute("UPDATE seats SET status=?, status_since=?, updated_at=? WHERE seat_id=?",
                  (new_status, now, now, seat_id))
        c.execute("INSERT INTO seat_events(seat_id, old_status, new_status, at) VALUES (?,?,?,?)",
                  (seat_id, old, new_status, now))
        return {"changed": True, "old": old, "new": new_status,
                "became_empty": new_status == AVAILABLE and old in (IN_USE, OCCUPIED)}


def get_seat(seat_id, path=None):
    """좌석 한 개 조회 (없으면 None). {"seat_id","floor","status","status_since"}"""
    with get_conn(path) as c:
        row = c.execute("SELECT seat_id, floor, status, status_since FROM seats WHERE seat_id=?",
                        (seat_id,)).fetchone()
    return dict(row) if row else None


def get_floor_seats(floor, path=None, now=None):
    """웹 화면용: 한 층의 좌석 현황. 프론트가 쓰는 모양 그대로 [{id, status, since, minutes}]"""
    with get_conn(path) as c:
        rows = c.execute(f"SELECT seat_id, status, status_since FROM seats WHERE floor=? {SEAT_ORDER}",
                         (int(floor),)).fetchall()
    return [{"id": r["seat_id"], "status": r["status"], "since": r["status_since"],
             "minutes": minutes_since(r["status_since"], now)} for r in rows]


def floor_counts(seats):
    """요약 카드용 개수: 전체 / 이용 가능 / 사용 중 / 점유 중"""
    return {"total": len(seats),
            AVAILABLE: sum(s["status"] == AVAILABLE for s in seats),
            IN_USE: sum(s["status"] == IN_USE for s in seats),
            OCCUPIED: sum(s["status"] == OCCUPIED for s in seats)}


def get_all_seats(path=None):
    with get_conn(path) as c:
        rows = c.execute(f"SELECT seat_id, floor, status, status_since FROM seats ORDER BY floor, "
                         f"CAST(substr(seat_id, instr(seat_id, '-') + 1) AS INTEGER)").fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# 사석화 판정 (점유 중이 1시간 이상 계속)
# ------------------------------------------------------------------
def find_sakhwa(path=None, now=None, threshold=SAKHWA_THRESHOLD):
    """occupied(점유 중)가 threshold 이상 이어졌고, 아직 이 점유 건으로 분실물 등록이 안 된 좌석."""
    now_dt = parse_time(now) if now else datetime.now().astimezone()
    found = []
    with get_conn(path) as c:
        rows = c.execute("SELECT seat_id, floor, status_since FROM seats WHERE status=?",
                         (OCCUPIED,)).fetchall()
        for r in rows:
            since = parse_time(r["status_since"])
            if now_dt - since < threshold:
                continue
            last = c.execute("SELECT registered_at FROM lost_items WHERE seat_id=? ORDER BY id DESC LIMIT 1",
                             (r["seat_id"],)).fetchone()
            if last and parse_time(last["registered_at"]) >= since:
                continue          # 이번 점유 건은 이미 분실물로 등록함
            found.append({"seat_id": r["seat_id"], "floor": r["floor"], "status_since": r["status_since"]})
    return found


# ------------------------------------------------------------------
# 분실물 (수거 물품 안내)
# ------------------------------------------------------------------
def register_lost_item(seat_id, image_path=None, path=None, now=None, note=None):
    """사석화로 판단된 좌석의 물품을 분실물(PENDING)로 등록. 새 분실물 id 반환.
    note: AI 가 감지한 물품 설명(관리자가 확인하면서 고칠 수 있음), image_path: 사진 파일 이름"""
    seat = get_seat(seat_id, path)
    if seat is None:
        raise KeyError(f"unknown seat: {seat_id}")
    with get_conn(path) as c:
        cur = c.execute("INSERT INTO lost_items(seat_id, floor, image_path, note, status, registered_at) "
                        "VALUES (?, ?, ?, ?, 'PENDING', ?)",
                        (seat_id, seat["floor"], image_path, note, now or _now()))
        return cur.lastrowid


def get_lost_item(item_id, path=None):
    """분실물 한 건 조회 (없으면 None)."""
    with get_conn(path) as c:
        row = c.execute("SELECT * FROM lost_items WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def admin_confirm_item(item_id, note=None, storage_place=None, path=None, now=None):
    """관리자가 확인(PENDING -> STORED). 학생 화면에 공개된다. 바뀌었으면 True."""
    with get_conn(path) as c:
        cur = c.execute("UPDATE lost_items SET status='STORED', handled_at=?, note=COALESCE(NULLIF(?, ''), note), storage_place=? "
                        "WHERE id=? AND status='PENDING'", (now or _now(), note, storage_place, item_id))
        return cur.rowcount > 0


def mark_claimed(item_id, path=None, now=None):
    """주인이 찾아감(STORED -> CLAIMED). 바뀌었으면 True."""
    with get_conn(path) as c:
        cur = c.execute("UPDATE lost_items SET status='CLAIMED', claimed_at=? "
                        "WHERE id=? AND status='STORED'", (now or _now(), item_id))
        return cur.rowcount > 0


def list_lost_items(status="STORED", path=None):
    """분실물 목록 (기본: 학생에게 보이는 STORED 만). status=None 이면 전부."""
    with get_conn(path) as c:
        if status is None:
            rows = c.execute("SELECT * FROM lost_items ORDER BY id DESC").fetchall()
        else:
            rows = c.execute("SELECT * FROM lost_items WHERE status=? ORDER BY id DESC", (status,)).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# 빈자리 알림 구독
# ------------------------------------------------------------------
def add_subscription(endpoint, p256dh, auth, seat_id=None, floor=None, path=None, now=None):
    if seat_id is None and floor is None:
        raise ValueError("seat_id 또는 floor 중 하나는 필요합니다")
    if seat_id is not None:
        target, floor = f"seat:{seat_id}", None
    else:
        floor = int(floor)
        target = f"floor:{floor}"
    with get_conn(path) as c:
        c.execute("""INSERT INTO push_subscriptions(endpoint, p256dh, auth, seat_id, floor, target, active, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                     ON CONFLICT(endpoint, target) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth, active=1""",
                  (endpoint, p256dh, auth, seat_id, floor, target, now or _now()))


def pop_subscribers(seat_id, path=None):
    """이 좌석이 비었을 때 알림을 받을 구독자를 꺼낸다(1회용: 꺼내면서 대기 상태를 해제).
    좌석을 직접 신청한 사람 + 그 층 전체를 신청한 사람. 같은 브라우저는 한 번만 알려준다."""
    seat = get_seat(seat_id, path)
    if seat is None:
        return []
    targets = (f"seat:{seat_id}", f"floor:{seat['floor']}")
    with get_conn(path) as c:
        rows = c.execute("SELECT id, endpoint, p256dh, auth FROM push_subscriptions "
                         "WHERE active=1 AND target IN (?, ?) ORDER BY id", targets).fetchall()
        c.executemany("UPDATE push_subscriptions SET active=0 WHERE id=?", [(r["id"],) for r in rows])
    seen, subs = set(), []
    for r in rows:
        if r["endpoint"] not in seen:
            seen.add(r["endpoint"])
            subs.append({"endpoint": r["endpoint"], "p256dh": r["p256dh"], "auth": r["auth"]})
    return subs


def remove_subscription(endpoint, path=None):
    """브라우저가 구독을 취소한 것으로 확인된 주소(푸시 서비스가 404/410 응답)를 정리한다."""
    with get_conn(path) as c:
        c.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
