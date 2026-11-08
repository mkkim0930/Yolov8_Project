"""
main.py  -  FastAPI 서버
========================

탐지 스크립트 -> (POST /seat-status) -> 이 서버 -> db.py -> library.db
웹 브라우저   <- (GET /floors/4, WebSocket /ws, 웹 푸시, GET /lost-items) <- 이 서버

프론트엔드(nari-library-share)가 쓰는 모양에 맞춘 API 입니다. 자세한 주고받는 내용은 API.md 를 보세요.

설치
----
pip install fastapi "uvicorn[standard]" pywebpush
(uvicorn[standard] 에 WebSocket 지원이 들어 있습니다)

실행
----
python setup_db.py --demo            # (처음 1번) 시험용 좌석 등록
uvicorn main:app --port 8000         # 서버 실행. 개발 중에 코드를 고치며 쓸 때만 --reload 추가

http://localhost:8000/docs 에서 모든 API 를 눌러서 시험해볼 수 있습니다.

환경 변수 (모두 선택)
--------------------
ADMIN_TOKEN        관리자 API 비밀번호. 미설정이면 관리자 API 는 모두 거부됩니다.
DETECTOR_KEY       탐지 프로그램 인증 키. 설정하면 POST /seat-status 에 같은 키(X-Detector-Key 헤더)가 있어야 합니다.
                   (탐지 프로그램은 --key 옵션 또는 같은 이름의 환경 변수로 보냄). 미설정이면 인증 없이 받습니다 = 내 컴퓨터에서만 쓸 때.
VAPID_PRIVATE_FILE 웹 푸시용 개인키 PEM 파일 경로  (gen_vapid.py 로 생성)
VAPID_PUBLIC_KEY   웹 푸시용 공개키 문자열         (gen_vapid.py 가 출력)
VAPID_EMAIL        연락용 메일 (mailto:...)
CORS_ORIGINS       화면 주소(쉼표 구분). 기본: http://localhost:5173,http://localhost:8000
SAKHWA_CHECK_SEC   사석화 검사 주기(초). 기본 60  (시연 때는 5 정도로)
SAKHWA_SECONDS     사석화로 볼 점유 중 지속 시간(초). 기본 3600(1시간)  (시연 때는 30 정도로)
PUSH_ALLOW_ANY     1 이면 푸시 주소 검사를 끔 (개발용. 기본: 실제 푸시 서비스 주소만 허용)

사석화 문자 알림 (모두 선택. SMS_PROVIDER 가 비어 있으면 문자를 보내지 않음)
SMS_PROVIDER       solapi(국내 문자) / twilio / log(실제로 보내지 않고 서버 창에 출력만. 시험용)
ADMIN_PHONE        받을 관리자 전화번호. 여러 명이면 쉼표로 구분 (예: 01012345678,01098765432)
SMS_FROM           보내는 번호 (솔라피는 사전 등록한 발신번호, 트윌리오는 트윌리오 번호)
SOLAPI_API_KEY / SOLAPI_API_SECRET     솔라피 콘솔의 API Key 관리에서 발급
TWILIO_SID / TWILIO_TOKEN              트윌리오 Account SID / Auth Token
ADMIN_URL          (선택) 문자에 같이 적을 관리자 확인 주소
DISABLE_DOCS       1 이면 /docs 화면을 끔 (공개 서버용)
"""

import asyncio
import base64
import binascii
import collections
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional
from urllib.parse import urlparse

from fastapi import (FastAPI, Header, HTTPException, Query, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
DETECTOR_KEY = os.environ.get("DETECTOR_KEY", "")
VAPID_PRIVATE_FILE = os.environ.get("VAPID_PRIVATE_FILE", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "mailto:admin@example.com")
SAKHWA_CHECK_SEC = int(os.environ.get("SAKHWA_CHECK_SEC", "60"))
SAKHWA_SECONDS = int(os.environ.get("SAKHWA_SECONDS", "3600"))   # 사석화 기준(초). 시연 때는 30 처럼 줄여서 실행
PUSH_ALLOW_ANY = os.environ.get("PUSH_ALLOW_ANY", "") == "1"
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",") if o.strip()]

# ---- 사석화 문자 알림 설정 ----
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "").strip().lower()      # "" / log / solapi / twilio
ADMIN_PHONES = [p for p in re.split(r"[,\s]+", os.environ.get("ADMIN_PHONE", "")) if p]
SMS_FROM = os.environ.get("SMS_FROM", "").strip()
SOLAPI_API_KEY = os.environ.get("SOLAPI_API_KEY", "")
SOLAPI_API_SECRET = os.environ.get("SOLAPI_API_SECRET", "")
TWILIO_SID = os.environ.get("TWILIO_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN", "")
ADMIN_URL = os.environ.get("ADMIN_URL", "").strip()
SOLAPI_URL = "https://api.solapi.com/messages/v4/send-many"
TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

# 브라우저가 푸시 구독 때 알려주는 주소는 크롬/엣지/파이어폭스/사파리의 푸시 서비스 주소여야 한다.
# (아무 주소나 받으면 서버가 그 주소로 요청을 보내게 되어 위험하다)
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com")
PUSH_HOST_SUFFIXES = (".push.services.mozilla.com", ".push.apple.com", ".notify.windows.com")


def is_allowed_push_endpoint(url: str) -> bool:
    if PUSH_ALLOW_ANY:
        return True
    try:
        u = urlparse(url)
        host = (u.hostname or "").lower()
        if u.scheme != "https" or not host or u.port not in (None, 443):
            return False
    except ValueError:
        return False
    return host in PUSH_HOSTS or host.endswith(PUSH_HOST_SUFFIXES)


def _same(a: Optional[str], b: str) -> bool:
    return bool(a) and secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_admin(token: Optional[str]):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="서버에 ADMIN_TOKEN 이 설정되지 않았습니다. "
                                                    "local_env.bat 을 확인하고 서버를 완전히 껐다가 다시 켜세요")
    if not _same(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="관리자 토큰이 올바르지 않습니다")


def require_detector(key: Optional[str]):
    if DETECTOR_KEY and not _same(key, DETECTOR_KEY):
        raise HTTPException(status_code=401, detail="탐지 프로그램 인증 키가 올바르지 않습니다")


# ------------------------------------------------------------------
# WebSocket 접속자 관리
# ------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.clients = []

    async def connect(self, ws):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, message: dict):
        text = json.dumps(message, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:            # 끊긴 접속은 조용히 제거
                self.disconnect(ws)


students = ConnectionManager()   # 학생용 화면
admins = ConnectionManager()     # 관리자 화면 (사석화 알림은 여기로만 보냄)

# 던져 놓은 백그라운드 작업은 참조를 쥐고 있어야 도중에 정리되지 않는다
background_tasks = set()


def spawn(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task


# ------------------------------------------------------------------
# 웹 푸시 (블로킹 라이브러리라 별도 스레드에서 실행)
# ------------------------------------------------------------------
def send_push_blocking(sub: dict, payload: dict) -> str:
    """반환: 'ok' / 'gone'(구독이 취소되어 더 보낼 수 없음) / 'fail'"""
    if not VAPID_PRIVATE_FILE:
        print("[push] VAPID 키가 설정되지 않아 푸시를 보내지 않습니다")
        return "fail"
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[push] pywebpush 가 설치되지 않았습니다 (pip install pywebpush)")
        return "fail"
    try:
        webpush(
            subscription_info={"endpoint": sub["endpoint"],
                               "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=VAPID_PRIVATE_FILE,
            vapid_claims={"sub": VAPID_EMAIL},
        )
        return "ok"
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        print(f"[push] 전송 실패: {e}")
        return "gone" if status in (404, 410) else "fail"
    except Exception as e:               # 키 파일을 못 찾음, 키 형식 오류 등 -> 원인을 터미널에 보여 준다
        print(f"[push] 오류 ({type(e).__name__}): {e}")
        return "fail"


async def push_to_subscribers(subs: list, payload: dict):
    loop = asyncio.get_running_loop()
    print(f"[push] {payload.get('seat_id')} 알림 신청자 {len(subs)}명에게 전송 시도")
    for sub in subs:
        result = await loop.run_in_executor(None, send_push_blocking, sub, payload)
        print(f"[push] 결과: {result}")
        if result == "gone":
            db.remove_subscription(sub["endpoint"])


# ------------------------------------------------------------------
# 사석화 문자 알림 (관리자에게 SMS)
# ------------------------------------------------------------------
def sms_config_problem() -> Optional[str]:
    """문자 설정에 문제가 있으면 이유를, 없으면 None 을 돌려준다 ('' 이면 기능 꺼짐)."""
    if not SMS_PROVIDER:
        return ""
    if SMS_PROVIDER not in ("log", "solapi", "twilio"):
        return f"SMS_PROVIDER 값이 올바르지 않습니다: {SMS_PROVIDER} (solapi / twilio / log)"
    if not ADMIN_PHONES:
        return "ADMIN_PHONE (받을 관리자 번호)이 없습니다"
    if SMS_PROVIDER == "solapi" and not (SOLAPI_API_KEY and SOLAPI_API_SECRET and SMS_FROM):
        return "솔라피는 SOLAPI_API_KEY, SOLAPI_API_SECRET, SMS_FROM(등록한 발신번호)이 모두 필요합니다"
    if SMS_PROVIDER == "twilio" and not (TWILIO_SID and TWILIO_TOKEN and SMS_FROM):
        return "트윌리오는 TWILIO_SID, TWILIO_TOKEN, SMS_FROM 이 모두 필요합니다"
    return None


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def _to_e164_kr(phone: str) -> str:
    """010-1234-5678 -> +821012345678 (트윌리오용). 이미 + 로 시작하면 그대로 둔다."""
    if phone.strip().startswith("+"):
        return "+" + _digits(phone)
    d = _digits(phone)
    return "+82" + d[1:] if d.startswith("0") else "+" + d


def build_sakhwa_text(found: list) -> str:
    """문자 내용. 짧게 유지한다(90바이트를 넘으면 긴 문자(LMS)로 나가 요금이 더 든다)."""
    ids = ", ".join(f"{seat['floor']}층 {seat['seat_id']}" for seat, _ in found)
    secs = SAKHWA_SECONDS
    dur = f"{secs // 60}분" if secs >= 60 else f"{secs}초"
    text = f"[책갈피] 사석화 감지: {ids} ({dur} 이상 점유). 수거 확인 필요"
    if ADMIN_URL:
        text += f" {ADMIN_URL}"
    return text


def _post(url: str, data: bytes, headers: dict, timeout: float = 10.0) -> tuple:
    """(성공 여부, 응답 앞부분). 비밀 값이 로그에 남지 않도록 요청 내용은 출력하지 않는다."""
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, r.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.read(300).decode('utf-8', 'replace')}"
    except Exception as e:                              # 인터넷 끊김, 시간 초과 등
        return False, f"{type(e).__name__}: {e}"


def _solapi_headers() -> dict:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    salt = secrets.token_hex(16)
    sig = hmac.new(SOLAPI_API_SECRET.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    return {"Authorization": f"HMAC-SHA256 apiKey={SOLAPI_API_KEY}, date={date}, salt={salt}, signature={sig}",
            "Content-Type": "application/json"}


def send_sms_blocking(text: str) -> list:
    """관리자 전원에게 문자를 보낸다. [(번호 끝 4자리, 성공 여부), ...] 를 돌려준다."""
    problem = sms_config_problem()
    if problem:
        print(f"[문자] 설정 문제로 보내지 않습니다: {problem}")
        return []
    if not SMS_PROVIDER:
        return []
    results = []
    if SMS_PROVIDER == "log":
        print(f"[문자:시험] 받는 사람 {len(ADMIN_PHONES)}명 / 내용: {text}")
        return [(_digits(p)[-4:], True) for p in ADMIN_PHONES]
    if SMS_PROVIDER == "solapi":
        body = json.dumps({"messages": [{"to": _digits(p), "from": _digits(SMS_FROM), "text": text}
                                        for p in ADMIN_PHONES]}, ensure_ascii=False).encode("utf-8")
        ok, info = _post(SOLAPI_URL, body, _solapi_headers())
        results = [(_digits(p)[-4:], ok) for p in ADMIN_PHONES]
        if not ok:
            print(f"[문자] 솔라피 전송 실패: {info}")
        return results
    # twilio: 번호마다 한 건씩
    auth = "Basic " + base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
    for p in ADMIN_PHONES:
        form = urllib.parse.urlencode({"To": _to_e164_kr(p), "From": SMS_FROM, "Body": text}).encode()
        ok, info = _post(TWILIO_URL.format(sid=TWILIO_SID), form,
                         {"Authorization": auth, "Content-Type": "application/x-www-form-urlencoded"})
        results.append((_digits(p)[-4:], ok))
        if not ok:
            print(f"[문자] 트윌리오 전송 실패 (…{_digits(p)[-4:]}): {info}")
    return results


async def notify_admin_sms(found: list):
    """사석화가 감지되면 관리자에게 문자를 보낸다 (이번 검사에서 찾은 좌석을 한 통으로 묶음)."""
    if not found or not SMS_PROVIDER:
        return
    text = build_sakhwa_text(found)
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, send_sms_blocking, text)
    if results:
        ok = sum(1 for _, good in results if good)
        print(f"[문자] 관리자 {len(results)}명 중 {ok}명 전송 성공")


# ------------------------------------------------------------------
# AI 가 감지한 물품(이름, 사진)을 기억해 두었다가 사석화가 확정되면 분실물로 자동 등록
# ------------------------------------------------------------------
UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
MAX_PHOTO_BYTES = 700_000
ITEM_NAMES_KO = {
    "backpack": "백팩", "handbag": "손가방", "suitcase": "캐리어", "umbrella": "우산",
    "book": "책", "laptop": "노트북", "cell phone": "휴대폰", "bottle": "물병", "cup": "컵",
    "mouse": "마우스", "keyboard": "키보드", "remote": "리모컨", "reserving": "물품",
}
seat_evidence = {}      # {seat_id: {"items": [이름...], "image": "파일이름.jpg" 또는 None}}  (서버를 끄면 사라지지만 탐지 프로그램이 다시 보냄)


def describe_items(names) -> str:
    """["book", "book", "laptop"] -> "책 2개, 노트북" (영어 클래스 이름은 한글로, 모르는 이름은 그대로)"""
    counts = collections.Counter(n for n in names if n)
    parts = []
    for name, n in counts.items():          # 처음 나온 순서 유지
        ko = ITEM_NAMES_KO.get(name, name)
        parts.append(f"{ko} {n}개" if n > 1 else ko)
    return ", ".join(parts)


def _save_photo(b64: str) -> Optional[str]:
    """base64 JPEG 를 검사한 뒤 추측하기 어려운 이름으로 저장하고 파일 이름을 돌려준다. 이상하면 None."""
    if not b64 or len(b64) > MAX_PHOTO_BYTES * 4 // 3 + 16:
        return None
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) > MAX_PHOTO_BYTES or not raw.startswith(b"\xff\xd8\xff"):      # JPEG 이 아니면 저장하지 않음
        return None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = secrets.token_urlsafe(12) + ".jpg"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(raw)
    return name


def _drop_photo(name: Optional[str]):
    if name and re.fullmatch(r"[A-Za-z0-9_-]{6,64}\.jpg", name):
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass


def remember_evidence(seat_id: str, items, image):
    """점유 중인 좌석에서 AI 가 본 물품을 기억한다 (가장 최근 것만 유지)."""
    try:
        names = [str(x).strip()[:40] for x in (items or [])[:20] if str(x).strip()]
        ev = seat_evidence.setdefault(seat_id, {"items": [], "image": None})
        if names:
            ev["items"] = names
        if image:
            new = _save_photo(image)
            if new:
                _drop_photo(ev["image"])        # 같은 좌석의 이전 사진은 지워서 파일이 쌓이지 않게 함
                ev["image"] = new
            else:
                print(f"[사진] {seat_id}: 사진 형식이 올바르지 않아 무시했습니다 (JPEG, {MAX_PHOTO_BYTES // 1000}KB 이하)")
    except Exception as e:                     # 사진/물품 기록이 실패해도 좌석 상태 반영은 막지 않는다
        print(f"[사진] {seat_id}: 기록 실패 - {type(e).__name__}: {e}")


def forget_evidence(seat_id: str):
    ev = seat_evidence.pop(seat_id, None)
    if ev:
        _drop_photo(ev.get("image"))


def with_image_url(item: dict) -> dict:
    d = dict(item)
    name = d.get("image_path")
    d["image_url"] = f"/lost-items/image/{name}" if name else None
    return d


# ------------------------------------------------------------------
# 사석화 검사 (백그라운드, 주기적으로)
# ------------------------------------------------------------------
async def check_sakhwa_once():
    """점유 중이 기준 시간(기본 1시간)을 넘은 좌석을 분실물로 등록하고 관리자에게 알린다."""
    found = []
    for seat in db.find_sakhwa(threshold=timedelta(seconds=SAKHWA_SECONDS)):
        ev = seat_evidence.pop(seat["seat_id"], None) or {}     # AI 가 감지해 둔 물품 이름과 사진
        what = describe_items(ev.get("items", []))
        note = f"{what} (AI 자동 감지)" if what else None
        item_id = db.register_lost_item(seat["seat_id"], image_path=ev.get("image"), note=note)
        found.append((seat, item_id))
        await admins.broadcast({
            "type": "sakhwa", "id": seat["seat_id"], "floor": seat["floor"],
            "since": seat["status_since"], "item_id": item_id, "note": note,
        })
    if found:
        spawn(notify_admin_sms(found))   # 관리자에게 문자 (설정했을 때만)
    return found


async def sakhwa_loop():
    while True:
        try:
            await check_sakhwa_once()
        except Exception as e:           # 한 번 실패해도 루프는 계속
            print(f"[sakhwa] 검사 오류: {e}")
        await asyncio.sleep(SAKHWA_CHECK_SEC)


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    if not DETECTOR_KEY:
        print("[보안] DETECTOR_KEY 가 없어 좌석 상태를 인증 없이 받습니다. 내 컴퓨터에서만 쓰세요. "
              "서버를 외부에 공개한다면 DETECTOR_KEY 를 설정하세요.")
    if ADMIN_TOKEN:
        print(f"[관리자] ADMIN_TOKEN 설정됨 (길이 {len(ADMIN_TOKEN)}자). 입력한 토큰의 글자 수와 다르면 공백이 섞인 것입니다")
    else:
        print("[관리자] ADMIN_TOKEN 이 없습니다 - 관리자 기능이 꺼져 있습니다")
    problem = sms_config_problem()
    if problem:
        print(f"[문자] 사석화 문자 알림이 꺼져 있습니다: {problem}")
    elif SMS_PROVIDER:
        print(f"[문자] 사석화 문자 알림 켜짐 ({SMS_PROVIDER}, 관리자 {len(ADMIN_PHONES)}명)")
    task = asyncio.create_task(sakhwa_loop())
    yield
    task.cancel()


_docs_off = os.environ.get("DISABLE_DOCS", "") == "1"
app = FastAPI(title="나리도서관 1인석 좌석 서비스", lifespan=lifespan,
              docs_url=None if _docs_off else "/docs",
              redoc_url=None, openapi_url=None if _docs_off else "/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
)


# ------------------------------------------------------------------
# 요청 본문 형식
# ------------------------------------------------------------------
class SeatStatus(BaseModel):
    seat_id: str                                              # 예: 4-01
    status: Literal["available", "inUse", "occupied"]         # 빈 자리 / 사용 중 / 점유 중
    items: Optional[List[str]] = None     # (선택) 점유 중일 때 AI 가 감지한 물품 이름들 (예: ["book", "book", "laptop"])
    image: Optional[str] = None           # (선택) 점유 중인 좌석 영역 사진 (JPEG 을 base64 로 인코딩)


class SubscribeBody(BaseModel):
    subscription: dict                 # 브라우저 pushManager.subscribe() 결과 그대로
    seat_id: Optional[str] = None      # 특정 좌석 알림 (예: 4-01)
    floor: Optional[int] = None        # 층 단위 알림 (예: 4)


class ConfirmBody(BaseModel):
    note: Optional[str] = None             # 물품 설명 (예: 검정 백팩)
    storage_place: Optional[str] = None    # 보관 장소 (예: 1층 안내데스크)


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/seat-status")
async def receive_seat_status(body: SeatStatus, x_detector_key: Optional[str] = Header(None)):
    """탐지 스크립트가 확정된 좌석 상태를 보내는 곳."""
    require_detector(x_detector_key)
    try:
        ev = db.update_seat_status(body.seat_id, body.status)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"등록되지 않은 좌석: {body.seat_id}")

    if body.status == "occupied":
        remember_evidence(body.seat_id, body.items, body.image)   # AI 가 본 물품 이름과 사진을 기억
    else:
        forget_evidence(body.seat_id)                             # 점유가 끝났으면 지움

    if ev["changed"]:
        seat = db.get_seat(body.seat_id)
        await students.broadcast({
            "type": "seat", "id": body.seat_id, "floor": seat["floor"],
            "status": body.status, "since": seat["status_since"], "minutes": 0,
        })
        if ev["became_empty"]:
            subs = db.pop_subscribers(body.seat_id)
            if subs:
                payload = {"title": "빈자리 알림",
                           "body": f"{seat['floor']}층 {body.seat_id} 좌석이 비었습니다.",
                           "seat_id": body.seat_id, "floor": seat["floor"]}
                spawn(push_to_subscribers(subs, payload))
    return ev


@app.get("/floors/{floor}")
def get_floor(floor: int):
    """한 층의 좌석 목록. 프론트가 쓰는 모양 그대로 + 요약 개수."""
    seats = db.get_floor_seats(floor)
    if not seats:
        raise HTTPException(status_code=404, detail=f"등록된 좌석이 없는 층입니다: {floor}층")
    return {"floor": floor, "seats": seats, "counts": db.floor_counts(seats)}


@app.get("/vapid-public-key")
def vapid_public_key():
    """프론트엔드가 푸시 구독을 만들 때 필요한 공개키."""
    return {"publicKey": VAPID_PUBLIC_KEY}


@app.post("/subscribe")
def subscribe(body: SubscribeBody):
    sub = body.subscription
    keys = sub.get("keys") or {}
    endpoint = sub.get("endpoint")
    if not (endpoint and keys.get("p256dh") and keys.get("auth")):
        raise HTTPException(status_code=422, detail="subscription 형식이 올바르지 않습니다")
    if not is_allowed_push_endpoint(endpoint):
        raise HTTPException(status_code=422, detail="허용되지 않는 푸시 주소입니다")
    if body.seat_id is None and body.floor is None:
        raise HTTPException(status_code=422, detail="seat_id 또는 floor 가 필요합니다")
    if body.seat_id is not None and db.get_seat(body.seat_id) is None:
        raise HTTPException(status_code=404, detail=f"등록되지 않은 좌석: {body.seat_id}")
    if body.seat_id is None and not db.get_floor_seats(body.floor):
        raise HTTPException(status_code=404, detail=f"등록된 좌석이 없는 층입니다: {body.floor}층")
    db.add_subscription(endpoint, keys["p256dh"], keys["auth"], seat_id=body.seat_id, floor=body.floor)
    return {"ok": True}


@app.get("/lost-items")
def lost_items():
    """수거 물품 안내 화면: 관리자가 확인한(STORED) 것만 보인다."""
    return {"items": [with_image_url(i) for i in db.list_lost_items("STORED")]}


@app.get("/lost-items/image/{name}")
def lost_item_image(name: str):
    """분실물 사진. 파일 이름이 추측하기 어려운 값이라, 목록에서 받은 주소로만 열 수 있다."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}\.jpg", name):
        raise HTTPException(status_code=404, detail="사진이 없습니다")
    path = os.path.join(UPLOAD_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="사진이 없습니다")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


# ---- 관리자 ----
@app.get("/admin/lost-items")
def admin_lost_items(status: str = "PENDING", x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    if status not in ("PENDING", "STORED", "CLAIMED", "ALL"):
        raise HTTPException(status_code=422, detail="status 는 PENDING / STORED / CLAIMED / ALL 중 하나")
    return {"items": [with_image_url(i) for i in db.list_lost_items(None if status == "ALL" else status)]}


@app.post("/admin/lost-items/{item_id}/confirm")
def admin_confirm(item_id: int, body: Optional[ConfirmBody] = None,
                  x_admin_token: Optional[str] = Header(None)):
    """관리자가 현장에서 확인 -> 학생에게 공개(STORED)."""
    require_admin(x_admin_token)
    body = body or ConfirmBody()
    if not db.admin_confirm_item(item_id, note=body.note, storage_place=body.storage_place):
        raise HTTPException(status_code=404, detail="확인 대기 중인 분실물을 찾을 수 없습니다")
    return {"ok": True}


@app.post("/admin/lost-items/{item_id}/claimed")
def admin_claimed(item_id: int, x_admin_token: Optional[str] = Header(None)):
    """주인이 찾아감(CLAIMED)."""
    require_admin(x_admin_token)
    item = db.get_lost_item(item_id)
    if not db.mark_claimed(item_id):
        raise HTTPException(status_code=404, detail="보관 중인 분실물을 찾을 수 없습니다")
    if item:
        _drop_photo(item.get("image_path"))     # 주인이 찾아갔으면 사진도 지운다
    return {"ok": True}


# ---- 실시간 ----
@app.websocket("/ws")
async def ws_students(ws: WebSocket):
    await students.connect(ws)
    try:
        while True:
            await ws.receive_text()      # 연결 유지용 (학생 쪽에서 오는 메시지는 사용하지 않음)
    except WebSocketDisconnect:
        students.disconnect(ws)


@app.websocket("/ws/admin")
async def ws_admin(ws: WebSocket, token: str = Query("")):
    if not ADMIN_TOKEN or not _same(token, ADMIN_TOKEN):
        await ws.close(code=1008)
        return
    await admins.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        admins.disconnect(ws)


# ---- 화면(프론트엔드) 제공 ----
# frontend 폴더를 같은 주소(/)에서 보여준다 (npm run build 로 만든 dist 의 내용을 여기에 넣으면 서버 하나로 시연 가능).
# (반드시 위의 API/WebSocket 경로보다 뒤에 있어야 한다. 그렇지 않으면 /floors 같은 요청을 가로챈다)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
