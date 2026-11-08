"""
seat_detector.py  -  YOLOv8 탐지 결과 -> 좌석 상태 -> 서버 전송
===============================================================

흐름
----
영상 프레임 -> YOLOv8(사람/짐 탐지, 모델 1개 또는 2개) -> 좌석 ROI 와 겹침 계산 -> 프레임별 상태(raw)
          -> 디바운싱(연속으로 같아야 확정) -> '바뀔 때만' 서버로 POST -> 서버가 DB 갱신

실행 예
-------
# 0) 먼저 학습한 모델의 클래스 이름 확인
python seat_detector.py --model best.pt --list-classes
python seat_detector.py --person-model person.pt --item-model reserving.pt --list-classes

# (A) 모델이 하나일 때 (한 모델 안에 sit down / reserving 이 모두 있음)
python seat_detector.py --model best.pt --seats seats.json --source test.mp4 --show --dry-run

# (B) 모델이 둘로 나뉘었을 때: 사람(sit down) 모델을 먼저 돌리고, 사람이 없는 좌석이 있을 때만 짐(reserving) 모델을 돌림
#     (매번 둘 다 돌리려면 --no-cascade)
python seat_detector.py --person-model person.pt --item-model reserving.pt \
       --seats seats.json --source test.mp4 --show --dry-run

# 서버로 전송하려면 --dry-run 대신  --server http://localhost:8000
# 시연용: 영상 파일을 재생 속도 그대로, 끝나면 반복  ->  --realtime --loop
# 모델마다 신뢰도를 따로 주려면  --person-conf 0.5 --item-conf 0.3
# 클래스 이름이 다르면 직접 지정 (공백이 있으면 따옴표로):  --person-classes "sit down" --item-classes "reserving"
# 기본 해석: sit down -> 사용 중(inUse), reserving -> 점유 중(occupied), 둘 다 없으면 빈 자리(available)

좌석 상태 값은 db.py·프론트엔드와 동일:  available(빈 자리) / inUse(사용 중) / occupied(점유 중)
서버로 보내는 내용: POST {server}/seat-status   {"seat_id": "4-03", "status": "available"}
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

import cv2

from roi_setup import camera_help, load_seats, open_capture

AVAILABLE, IN_USE, OCCUPIED = "available", "inUse", "occupied"   # 빈 자리 / 사용 중 / 점유 중

PREDICT_OPTS = {}   # 속도 옵션(--imgsz, --device)이 여기에 들어가 모든 탐지 호출에 전달된다


# ------------------------------------------------------------------
# 1. 탐지 결과 -> 좌석 매핑
# ------------------------------------------------------------------
def overlap_ratio(det_box, roi):
    """탐지 박스 면적 중 좌석 ROI 와 겹친 비율(0~1).
    (일반 IoU 는 박스가 ROI 보다 크면 값이 낮게 나와서 이 방식을 사용)"""
    ix = max(0, min(det_box[2], roi[2]) - max(det_box[0], roi[0]))
    iy = max(0, min(det_box[3], roi[3]) - max(det_box[1], roi[1]))
    area = (det_box[2] - det_box[0]) * (det_box[3] - det_box[1])
    return (ix * iy) / area if area > 0 else 0.0


def assign_detections(dets, seats, min_overlap=0.3):
    """각 탐지를 '가장 많이 겹치는 좌석 하나'에만 배정한다(옆 좌석 이중 카운트 방지).
    dets : [{"kind": "person"|"item", "box": [x1,y1,x2,y2]}, ...]
    반환 : {seat_id: {"person": bool, "item": bool}}
    """
    flags = {sid: {"person": False, "item": False} for sid in seats}
    for d in dets:
        best_sid, best = None, 0.0
        for sid, roi in seats.items():
            r = overlap_ratio(d["box"], roi)
            if r > best:
                best_sid, best = sid, r
        if best_sid is not None and best >= min_overlap:
            flags[best_sid][d["kind"]] = True
    return flags


def raw_status(f):
    """한 프레임의 좌석 상태. 사람이 있으면 사용 중, 사람 없이 짐만 있으면 점유 중."""
    if f["person"]:
        return IN_USE
    if f["item"]:
        return OCCUPIED
    return AVAILABLE


def items_by_seat(dets, seats, min_overlap=0.3):
    """좌석마다 '짐(item)' 탐지의 클래스 이름을 모은다. 같은 물건이 여러 개면 이름이 여러 번 들어간다.
    반환: {seat_id: ["book", "book", "laptop"]}  (assign_detections 와 같은 규칙으로 좌석에 배정)"""
    out = {sid: [] for sid in seats}
    for d in dets:
        if d.get("kind") != "item":
            continue
        best_sid, best = None, 0.0
        for sid, roi in seats.items():
            r = overlap_ratio(d["box"], roi)
            if r > best:
                best_sid, best = sid, r
        if best_sid is not None and best >= min_overlap:
            out[best_sid].append(str(d.get("name") or "item"))
    return out


def make_photo(frame, roi, margin=0.15, max_w=480, quality=70):
    """좌석 영역(조금 넓게)을 잘라 JPEG -> base64 문자열로 만든다. 실패하면 None.
    개인정보를 줄이기 위해 전체 화면이 아니라 좌석 영역만 저장한다."""
    try:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = roi
        mx, my = int((x2 - x1) * margin), int((y2 - y1) * margin)
        x1, y1, x2, y2 = max(0, x1 - mx), max(0, y1 - my), min(w, x2 + mx), min(h, y2 + my)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None
        crop = frame[y1:y2, x1:x2]
        if crop.shape[1] > max_w:
            scale = max_w / crop.shape[1]
            crop = cv2.resize(crop, (max_w, max(1, int(crop.shape[0] * scale))))
        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None
    except Exception as e:
        print(f"[사진] 만들기 실패: {e}")
        return None


# ------------------------------------------------------------------
# 2. 디바운싱: 같은 결과가 연속으로 나올 때만 상태를 바꾼다
# ------------------------------------------------------------------
def default_confirm_ticks(old, new):
    """상태가 바뀌기까지 필요한 '연속 횟수'(추론 1회 = --interval 초).
    앉은 것은 확실한 신호라 빨리, 일어난 것은 자세 변화로 놓칠 수 있어 천천히."""
    if old is None:
        return 3          # 첫 상태 확정
    if new == IN_USE:
        return 3          # 사람이 나타남 -> 빠르게
    if old == IN_USE:
        return 10         # 사람이 사라짐 -> 느리게 (고개 숙임/가림 오탐 방지)
    return 5              # 빈자리 <-> 점유중


class Debouncer:
    def __init__(self, confirm_fn=default_confirm_ticks):
        self.confirm_fn = confirm_fn
        self.state = None      # 확정된 상태
        self.cand = None       # 바뀔 후보 상태
        self.count = 0

    def update(self, raw):
        """raw 를 받아 (확정 상태, 이번에 바뀌었는지) 반환. 확정 전이면 (None, False)."""
        if self.state is not None and raw == self.state:
            self.cand, self.count = None, 0
            return self.state, False
        if raw == self.cand:
            self.count += 1
        else:
            self.cand, self.count = raw, 1
        if self.count >= self.confirm_fn(self.state, raw):
            self.state, self.cand, self.count = raw, None, 0
            return self.state, True
        return self.state, False


# ------------------------------------------------------------------
# 3. 서버 전송: 바뀔 때만 보내고, 실패하면 다음 턴에 재시도, 주기적으로 생존 신호
# ------------------------------------------------------------------
class Sender:
    def __init__(self, server, dry_run=False, timeout=3.0, heartbeat=30.0, key=None):
        self.key = key         # 서버에 DETECTOR_KEY 가 설정되어 있을 때 보내는 인증 키
        self.url = (server or "").rstrip("/") + "/seat-status"
        self.dry_run = dry_run
        self.timeout = timeout
        self.heartbeat = heartbeat
        self.pending = {}      # {seat_id: {"status", "items", "image"}}  아직 못 보낸 것
        self.last_sent = {}    # {seat_id: (status, time)}
        self.last_items = {}   # {seat_id: [물품 이름]}  생존 신호에도 같이 보냄

    def queue(self, seat_id, status, items=None, image=None):
        """items: 점유 중일 때 AI 가 감지한 물품 이름들, image: 좌석 영역 사진(base64 JPEG)"""
        old = self.pending.get(seat_id)
        if old and old["status"] == status:        # 같은 상태면 아직 못 보낸 사진/물품 정보를 잃지 않게 합친다
            items = items if items is not None else old["items"]
            image = image if image is not None else old["image"]
        self.pending[seat_id] = {"status": status, "items": items, "image": image}
        if status == OCCUPIED and items is not None:
            self.last_items[seat_id] = items
        elif status != OCCUPIED:
            self.last_items.pop(seat_id, None)

    def _post(self, seat_id, status, items=None, image=None):
        """반환: True=전송 성공, False=나중에 다시 시도, None=서버가 거절해서 버림(재시도 무의미)"""
        if self.dry_run:
            extra = f" (물품: {items}{', 사진 포함' if image else ''})" if items or image else ""
            print(f"[dry-run] {seat_id} -> {status}{extra}")
            return True
        payload = {"seat_id": seat_id, "status": status}
        if items:
            payload["items"] = items
        if image:
            payload["image"] = image
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["X-Detector-Key"] = self.key
        req = urllib.request.Request(self.url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return 200 <= r.status < 300
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                # 서버가 '이 요청 자체가 잘못됨'이라고 거절한 것 -> 재시도해도 소용없으므로 버린다.
                # (버리지 않으면 같은 메시지를 영원히 재시도하며 뒤의 좌석 전송까지 막힌다)
                hints = {
                    401: "서버가 인증 키를 요구합니다. 서버의 DETECTOR_KEY 와 같은 값을 --key 옵션(또는 환경변수 DETECTOR_KEY)으로 주세요",
                    404: "서버 DB 에 없는 좌석입니다. seats.json 의 좌석 이름과 서버에 등록한 이름이 같은지 확인하세요",
                    422: "서버가 이 상태 값을 받아들이지 않았습니다. 서버의 main.py / db.py 가 최신 버전"
                         "(available / inUse / occupied)인지 확인하고 서버를 껐다 다시 켜세요",
                }
                print(f"[전송 거절 {e.code}] {seat_id}={status} 버림 - {hints.get(e.code, '서버 응답을 확인하세요')}")
                try:
                    detail = e.read().decode("utf-8", "replace").strip()[:300]
                except Exception:
                    detail = ""
                if detail:
                    print(f"    서버 응답: {detail}")
                return None
            print(f"[서버 오류 {e.code}] {seat_id}: 다음 턴에 재시도")
            return False
        except (urllib.error.URLError, OSError) as e:
            print(f"[전송 실패] {seat_id}: {e}  (다음 턴에 재시도)")
            return False

    def flush(self, now=None):
        now = time.time() if now is None else now
        # 생존 신호: 오래 안 보낸 좌석은 현재 상태를 한 번 더 보내 서버가 '카메라 살아있음'을 알게 함
        for sid, (st, t) in list(self.last_sent.items()):
            if now - t >= self.heartbeat and sid not in self.pending:
                self.pending[sid] = {"status": st, "items": self.last_items.get(sid), "image": None}
        for sid, p in list(self.pending.items()):
            st = p["status"]
            res = self._post(sid, st, p["items"], p["image"])
            if res is False:
                break   # 서버가 죽어 있으면 좌석마다 timeout 을 기다리지 않고 중단
            del self.pending[sid]
            if res:
                self.last_sent[sid] = (st, now)
            else:
                self.last_sent.pop(sid, None)   # 거절된 좌석은 생존 신호로 같은 요청을 되풀이하지 않는다


# ------------------------------------------------------------------
# 4. 보조 함수
# ------------------------------------------------------------------
def realtime_delay(frame_idx, fps, start, now):
    """영상 파일을 '재생 속도 그대로' 처리하기 위해 지금 쉬어야 할 시간(초).
    frame_idx 번째 프레임은 영상 시작 후 frame_idx/fps 초에 보여야 한다."""
    return max(0.0, start + frame_idx / fps - now)


def fit_frame(frame, size):
    """ROI 를 그린 해상도와 다르면 그 해상도로 맞춘다(좌표가 어긋나는 것 방지)."""
    if size and (frame.shape[1], frame.shape[0]) != tuple(size):
        return cv2.resize(frame, tuple(size))
    return frame


def _parse_names(arg):
    return [x.strip() for x in arg.split(",") if x.strip()]


def resolve_class_ids(names, arg, label=""):
    """쉼표로 적은 클래스 이름들을 '그 모델'의 클래스 번호로 바꾼다.
    이름이 모델에 없으면(가장 흔한 실수) 그 모델의 전체 이름 목록을 보여주고 중단."""
    name2id = {v: k for k, v in names.items()}
    wanted = _parse_names(arg)
    missing = [n for n in wanted if n not in name2id]
    if missing:
        print(f"[오류] {label}모델에 없는 클래스 이름: {missing}")
        print(f"        이 모델의 클래스: {dict(names)}")
        print("        --person-classes / --item-classes 를 위 이름에 맞게 지정하세요.")
        sys.exit(1)
    return {name2id[n] for n in wanted}


def resolve_classes(names, person_arg, item_arg):
    """모델 1개에서 사람/짐 클래스 번호를 한꺼번에 구한다."""
    return resolve_class_ids(names, person_arg), resolve_class_ids(names, item_arg)


def extract_detections(result, kinds):
    """모델 결과 1개에서 관심 클래스만 [{kind, box}] 로 뽑는다.
    kinds: {클래스번호: "person"|"item"}.
    ※ 클래스 번호는 모델마다 따로 매겨지므로(두 모델 모두 0번이 있을 수 있음) 반드시 모델별로 따로 변환한다."""
    dets = []
    names = getattr(result, "names", None) or {}
    for b in result.boxes:
        cid = int(b.cls[0])
        kind = kinds.get(cid)
        if kind:
            x1, y1, x2, y2 = map(int, b.xyxy[0])
            conf = float(b.conf[0]) if getattr(b, "conf", None) is not None else None
            dets.append({"kind": kind, "box": [x1, y1, x2, y2],
                         "name": names.get(cid, kind), "conf": conf})
    return dets


class Detector:
    """모델 1개(사람+짐 모두) 또는 2개(사람 모델 + 짐 모델)를 같은 방식으로 다룬다."""

    def __init__(self, passes):
        self.passes = passes          # [(model, {클래스번호: kind}, conf), ...]

    def detect(self, frame, seats=None, min_overlap=0.3):
        dets = []
        for model, kinds, conf in self.passes:
            dets += extract_detections(model.predict(frame, conf=conf, verbose=False, **PREDICT_OPTS)[0], kinds)
        return dets


class CascadeDetector:
    """1단계: 사람 모델로 사람부터 찾는다.
    2단계: 사람이 없는 좌석이 하나라도 있을 때만 짐 모델을 돌린다(모든 좌석에 사람이 있으면 건너뜀).
    그리고 사람이 있는 좌석에서 나온 짐 탐지는 버린다 -> '사람이 없을 때만 책상 위 물건을 본다'."""

    def __init__(self, person_pass, item_pass):
        self.person_pass = person_pass     # (model, {클래스번호: "person"}, conf)
        self.item_pass = item_pass         # (model, {클래스번호: "item"},   conf)
        self.ticks = 0                     # 전체 추론 횟수
        self.item_runs = 0                 # 그중 짐 모델까지 돌린 횟수

    def detect(self, frame, seats=None, min_overlap=0.3):
        self.ticks += 1
        model, kinds, conf = self.person_pass
        dets = extract_detections(model.predict(frame, conf=conf, verbose=False, **PREDICT_OPTS)[0], kinds)
        if not seats:                      # 좌석 정보가 없으면 판단 불가 -> 짐 모델도 돌린다
            seats = {}
        flags = assign_detections(dets, seats, min_overlap)
        free = [sid for sid in seats if not flags[sid]["person"]]
        if seats and not free:             # 모든 좌석에 사람이 있음 -> 짐 모델 생략
            return dets
        self.item_runs += 1
        model, kinds, conf = self.item_pass
        items = extract_detections(model.predict(frame, conf=conf, verbose=False, **PREDICT_OPTS)[0], kinds)
        # 사람이 있는 좌석에 배정되는 짐은 무시 (사람 없는 좌석에서 나온 짐만 남김)
        if seats:
            keep = []
            for d in items:
                best_sid, best = None, 0.0
                for sid, roi in seats.items():
                    r = overlap_ratio(d["box"], roi)
                    if r > best:
                        best_sid, best = sid, r
                if best_sid is None or best_sid in free:
                    keep.append(d)
            items = keep
        return dets + items


def build_detector(args, load_model):
    """실행 옵션에 맞게 Detector 를 만든다. load_model(경로) -> 모델 (ultralytics.YOLO 등)."""
    person_conf = args.person_conf if args.person_conf is not None else args.conf
    item_conf = args.item_conf if args.item_conf is not None else args.conf

    if args.model and (args.person_model or args.item_model):
        sys.exit("[오류] --model 과 --person-model/--item-model 은 함께 쓸 수 없습니다. 둘 중 하나만 지정하세요.")

    if args.model:                                     # (A) 한 모델에 사람/짐 클래스가 모두 있는 경우
        m = load_model(args.model)
        kinds = {i: "person" for i in resolve_class_ids(m.names, args.person_classes)}
        kinds.update({i: "item" for i in resolve_class_ids(m.names, args.item_classes)})
        return Detector([(m, kinds, args.conf)])

    if args.person_model and args.item_model:          # (B) 모델이 둘로 나뉜 경우
        same = os.path.abspath(args.person_model) == os.path.abspath(args.item_model)
        pm = load_model(args.person_model)
        im = pm if same else load_model(args.item_model)
        pk = {i: "person" for i in resolve_class_ids(pm.names, args.person_classes, "사람 ")}
        ik = {i: "item" for i in resolve_class_ids(im.names, args.item_classes, "짐 ")}
        if same:                                       # 같은 파일을 두 번 적었다면 한 번만 돌린다
            return Detector([(pm, {**pk, **ik}, min(person_conf, item_conf))])
        if getattr(args, "no_cascade", False):         # 매번 두 모델을 모두 돌리는 예전 방식
            return Detector([(pm, pk, person_conf), (im, ik, item_conf)])
        return CascadeDetector((pm, pk, person_conf), (im, ik, item_conf))

    sys.exit("[오류] --model 하나, 또는 --person-model 과 --item-model 을 함께 지정하세요.")


STATE_COLOR = {IN_USE: (0, 0, 255), OCCUPIED: (0, 200, 255), AVAILABLE: (0, 220, 0), None: (160, 160, 160)}
STATE_LABEL = {IN_USE: "IN USE", OCCUPIED: "OCCUPIED", AVAILABLE: "AVAILABLE", None: "..."}


DET_COLOR = {"person": (255, 120, 0), "item": (200, 0, 200)}   # 사람=파랑 계열, 짐=보라 (BGR)


def draw(frame, seats, debouncers, dets, info=""):
    img = frame.copy()
    # 좌석 영역과 확정된 상태
    for sid, (x1, y1, x2, y2) in seats.items():
        st = debouncers[sid].state
        c = STATE_COLOR[st]
        cv2.rectangle(img, (x1, y1), (x2, y2), c, 2)
        cv2.putText(img, f"{sid} {STATE_LABEL[st]}", (x1 + 4, y1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 2, cv2.LINE_AA)
    # AI 가 찾은 것: 박스 + "이름 확신도"
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        c = DET_COLOR.get(d["kind"], (255, 255, 255))
        cv2.rectangle(img, (x1, y1), (x2, y2), c, 3)
        label = d.get("name", d["kind"])
        if d.get("conf") is not None:
            label += f" {d['conf']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        ty = max(th + 6, y1)
        cv2.rectangle(img, (x1, ty - th - 6), (x1 + tw + 8, ty), c, -1)
        cv2.putText(img, label, (x1 + 4, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    if info:
        cv2.putText(img, info, (10, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, info, (10, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return img


# ------------------------------------------------------------------
# 5. 메인
# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="YOLOv8 좌석 탐지 + 서버 전송")
    ap.add_argument("--model", default=None, help="사람+짐 클래스가 한 모델에 있을 때: 가중치 (예: best.pt)")
    ap.add_argument("--person-model", default=None, help="모델이 둘로 나뉘었을 때: 사람(sit down) 모델 가중치")
    ap.add_argument("--item-model", default=None, help="모델이 둘로 나뉘었을 때: 짐(reserving) 모델 가중치")
    ap.add_argument("--seats", default="seats.json")
    ap.add_argument("--source", default="0", help="영상 파일 / 웹캠 번호 / RTSP 주소")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--key", default=os.environ.get("DETECTOR_KEY"),
                    help="서버 인증 키 (서버에 DETECTOR_KEY 를 설정했을 때만 필요. 환경변수 DETECTOR_KEY 로도 가능)")
    ap.add_argument("--person-classes", default="sit down",
                    help="'사용중'으로 볼 클래스 이름(쉼표 구분). 기본: sit down")
    ap.add_argument("--item-classes", default="reserving",
                    help="'점유중(사석화)'으로 볼 클래스 이름(쉼표 구분). 기본: reserving")
    ap.add_argument("--conf", type=float, default=0.4, help="탐지 신뢰도 기준")
    ap.add_argument("--person-conf", type=float, default=None, help="사람 모델 신뢰도 기준 (없으면 --conf)")
    ap.add_argument("--item-conf", type=float, default=None, help="짐 모델 신뢰도 기준 (없으면 --conf)")
    ap.add_argument("--no-cascade", action="store_true",
                    help="두 모델을 항상 모두 돌린다 (기본: 사람 먼저 -> 사람 없는 좌석이 있을 때만 짐 모델)")
    ap.add_argument("--overlap", type=float, default=0.3, help="좌석으로 인정할 겹침 비율")
    ap.add_argument("--interval", type=float, default=1.0, help="추론 간격(초)")
    ap.add_argument("--imgsz", type=int, default=None,
                    help="탐지에 쓰는 이미지 크기. 작을수록 빠름 (예: 416, 320). 기본 640")
    ap.add_argument("--device", default=None, help="추론 장치 (예: cpu, 0 = 첫 번째 GPU). 기본: 자동")
    ap.add_argument("--photo-every", type=float, default=300.0,
                    help="점유 중인 좌석의 사진을 서버에 갱신해 보내는 주기(초). 기본 300 (처음 점유가 확정될 때는 바로 보냄)")
    ap.add_argument("--photo", action="store_true", help="물품 이름과 함께 좌석 영역 사진도 보냄 (기본: 사진 없이 이름만)")
    ap.add_argument("--heartbeat", type=float, default=30.0, help="생존 신호 주기(초)")
    ap.add_argument("--show", action="store_true", help="감지 창을 띄워 박스와 좌석 상태를 보여 줌 (q 로 종료)")
    ap.add_argument("--live", action="store_true",
                    help="감지 창의 박스를 매 프레임 실시간으로 갱신 (좌석 상태 확정은 그대로 --interval 간격. 컴퓨터가 느리면 끊길 수 있음)")
    ap.add_argument("--realtime", action="store_true",
                    help="영상 파일을 재생 속도 그대로 처리 (시연용. 없으면 컴퓨터가 가능한 최고 속도로 처리)")
    ap.add_argument("--loop", action="store_true", help="영상 파일이 끝나면 처음부터 반복 (시연용)")
    ap.add_argument("--dry-run", action="store_true", help="서버로 보내지 않고 출력만")
    ap.add_argument("--list-classes", action="store_true", help="모델의 클래스 이름만 출력하고 종료")
    args = ap.parse_args()

    from ultralytics import YOLO          # 여기서 불러와 다른 기능은 YOLO 없이도 테스트 가능
    if args.list_classes:
        for label, path in (("모델", args.model), ("사람 모델", args.person_model), ("짐 모델", args.item_model)):
            if path:
                print(f"{label} 클래스:", dict(YOLO(path).names))
        return
    if args.imgsz:
        PREDICT_OPTS["imgsz"] = args.imgsz
    if args.device:
        PREDICT_OPTS["device"] = args.device
    detector = build_detector(args, YOLO)

    seats, size, cam = load_seats(args.seats)
    print(f"좌석 {len(seats)}개 로드 (camera={cam or '-'}, ROI 해상도={size})")

    is_file = os.path.isfile(args.source)
    cap = open_capture(args.source)
    if cap is None:
        sys.exit(camera_help(args.source))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    stride = max(1, int(round(fps * args.interval))) if is_file else None

    debouncers = {sid: Debouncer() for sid in seats}
    sender = Sender(args.server, dry_run=args.dry_run, heartbeat=args.heartbeat, key=args.key)
    last_t, idx, dets = 0.0, 0, []
    seen_items = {}      # {seat_id: 마지막으로 본 물품 이름들} 점유 중인 좌석만
    last_photo = {}      # {seat_id: 마지막 사진 전송 시각}
    shown_fps, prev_t = 0.0, time.time()

    start = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            if args.loop and is_file and idx > 0:       # 끝났으면 처음으로 되감아 반복
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                idx, start = 0, time.time()
                continue
            if idx == 0:
                print("[오류] 첫 화면을 읽지 못했습니다. 다른 프로그램이 카메라를 쓰고 있거나 카메라 권한이 꺼져 있을 수 있습니다.")
            break
        idx += 1
        if is_file and args.realtime:
            time.sleep(realtime_delay(idx, fps, start, time.time()))

        # AI 추론은 --interval 초마다 한 번만 하되, 화면(--show)은 매 프레임 갱신해서 끊김 없이 보여 준다
        if is_file:
            do_infer = (idx % stride == 0)           # 영상 파일: interval 초에 해당하는 프레임 간격
        else:
            do_infer = (time.time() - last_t >= args.interval)   # 카메라: 시간 간격
            if do_infer:
                last_t = time.time()

        if do_infer or args.show:
            frame = fit_frame(frame, size)

        if do_infer or (args.show and args.live):
            dets = detector.detect(frame, seats, args.overlap)   # --live 이면 화면용으로 매 프레임 탐지

        if do_infer:                  # 좌석 상태 확정/전송은 항상 --interval 간격으로만
            flags = assign_detections(dets, seats, args.overlap)
            names_now = items_by_seat(dets, seats, args.overlap)
            for sid in seats:
                state, changed = debouncers[sid].update(raw_status(flags[sid]))
                if state == OCCUPIED:
                    prev_items = seen_items.get(sid)
                    if names_now[sid]:                       # 한 순간 안 보여도 마지막으로 본 물품을 유지
                        seen_items[sid] = names_now[sid]
                    items_changed = seen_items.get(sid) != prev_items
                    photo = None
                    if (args.photo and seen_items.get(sid)
                            and time.time() - last_photo.get(sid, 0) >= args.photo_every):
                        photo = make_photo(frame, seats[sid])
                        if photo:
                            last_photo[sid] = time.time()
                    if changed or photo or items_changed:
                        if changed:
                            print(f"[{time.strftime('%H:%M:%S')}] {sid}: {state}  물품: {seen_items.get(sid) or '-'}")
                        sender.queue(sid, state, items=seen_items.get(sid), image=photo)
                else:
                    seen_items.pop(sid, None)
                    last_photo.pop(sid, None)
                    if changed:
                        print(f"[{time.strftime('%H:%M:%S')}] {sid}: {state}")
                        sender.queue(sid, state)
            sender.flush()

        if args.show:
            # 박스와 좌석 색은 가장 최근 추론 결과를 사용 (추론 사이의 프레임에는 이전 결과를 그대로 얹음)
            now_t = time.time()
            shown_fps = 0.9 * shown_fps + 0.1 / max(now_t - prev_t, 1e-6) if shown_fps else 1.0 / max(now_t - prev_t, 1e-6)
            prev_t = now_t
            mode = "LIVE" if args.live else f"detect every {args.interval:g}s"
            cv2.imshow("Seat Detector", draw(frame, seats, debouncers, dets,
                                             f"{mode} | {shown_fps:.0f} FPS | q: quit"))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    sender.flush()
    if isinstance(detector, CascadeDetector) and detector.ticks:
        print(f"짐 모델 실행 {detector.item_runs}/{detector.ticks}회 "
              f"(나머지는 모든 좌석에 사람이 있어 생략)")
    print("종료")


if __name__ == "__main__":
    main()
