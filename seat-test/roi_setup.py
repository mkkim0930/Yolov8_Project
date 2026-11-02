"""
roi_setup.py  -  좌석 영역(ROI) 설정 도구
==========================================

카메라 화면 위에서 마우스로 좌석 영역을 그리고 seats.json 으로 저장합니다.
(탐지 스크립트는 이 seats.json 을 읽어서 좌석별 상태를 판별합니다.)

실행 예
-------
python roi_setup.py --source snapshot.jpg --prefix 4-           # 이미지 한 장으로 (4층이면 4- , 좌석은 4-01, 4-02 ...)
python roi_setup.py --source test_video.mp4 --prefix 4-         # 영상에서 프레임 골라서
python roi_setup.py --source rtsp://IP:PORT/stream --prefix 4-  # 실시간 카메라
python roi_setup.py --source test_video.mp4 --load seats.json   # 기존 설정 이어서 수정

조작법
------
  마우스 왼쪽 드래그 : 좌석 영역 그리기 (좌석 번호는 자동으로 4-01, 4-02 ... 순서대로 부여)
  마우스 오른쪽 클릭 : 클릭한 위치의 좌석 삭제
  r                 : 마지막으로 그린 좌석의 이름을 직접 바꾸기 (터미널에서 입력)
  z                 : 마지막 좌석 취소 (undo)
  n                 : 다음 프레임으로 (영상/카메라일 때. 사람이 없는 장면을 고를 때 사용)
  s                 : seats.json 저장
  q                 : 종료

그리는 요령
-----------
  * 책상 + 의자 부분을 함께 감싸게 그리세요. (짐은 책상 위, 사람은 의자 쪽에 있습니다)
  * 옆 좌석 영역과 겹치지 않게 그리세요. 겹치면 빨간색으로 표시됩니다.
  * 항상 같은 순서(예: 왼쪽 → 오른쪽)로 그리면 번호 관리가 쉽습니다.
  * 카메라 위치가 바뀌면 ROI 를 다시 잡아야 합니다.

저장 형식 (seats.json)
----------------------
{
  "camera_id": "4F-cam1",
  "frame_size": [1280, 720],      <- ROI 를 그린 화면 해상도 (탐지할 때 같은 해상도여야 함)
  "seats": {
    "4-01": [x1, y1, x2, y2],
    ...
  }
}
"""

import argparse
import json
import os
import sys
import time

import cv2

MIN_SIZE = 12            # 이보다 작은 사각형은 클릭 실수로 보고 무시
OVERLAP_WARN = 0.10      # 두 ROI 가 작은 쪽 면적의 10% 이상 겹치면 경고


# ------------------------------------------------------------------
# 순수 로직 (화면 없이도 동작 / 테스트 가능)
# ------------------------------------------------------------------
def overlap_ratio_between(a, b):
    """두 사각형이 겹치는 면적을 '더 작은 사각형 면적'으로 나눈 비율(0~1)."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / min(area_a, area_b)


def load_seats(path):
    """seats.json 을 읽어 (좌석 dict, frame_size, camera_id) 를 돌려준다.
    탐지 스크립트에서도 이 함수를 import 해서 쓰면 된다."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    seats = {sid: [int(v) for v in box] for sid, box in data["seats"].items()}
    frame_size = tuple(data["frame_size"]) if data.get("frame_size") else None
    return seats, frame_size, data.get("camera_id", "")


class SeatEditor:
    """ROI 편집 상태와 동작. GUI 와 분리되어 있어 마우스 이벤트만 넣어주면 동작한다."""

    def __init__(self, frame, prefix="A-", camera_id="", seats=None):
        self.frame = frame
        self.h, self.w = frame.shape[:2]
        self.prefix = prefix
        self.camera_id = camera_id
        self.seats = dict(seats) if seats else {}   # 삽입 순서 유지 (undo 에 사용)
        self.drawing = False
        self.p1 = (0, 0)
        self.p2 = (0, 0)
        self.message = ""

    # ---- 번호 ----
    def next_id(self):
        n = 1
        while f"{self.prefix}{n:02d}" in self.seats:
            n += 1
        return f"{self.prefix}{n:02d}"

    # ---- 좌표 보정 ----
    def _clamp(self, x, y):
        return max(0, min(self.w - 1, x)), max(0, min(self.h - 1, y))

    # ---- 마우스 ----
    def on_mouse(self, event, x, y):
        x, y = self._clamp(x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.p1 = self.p2 = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.p2 = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.drawing:
            self.drawing = False
            self.p2 = (x, y)
            self._commit()
        elif event == cv2.EVENT_RBUTTONDOWN:
            self._delete_at(x, y)

    def _commit(self):
        x1, x2 = sorted([self.p1[0], self.p2[0]])
        y1, y2 = sorted([self.p1[1], self.p2[1]])
        if (x2 - x1) < MIN_SIZE or (y2 - y1) < MIN_SIZE:
            self.message = "too small - ignored"
            return
        sid = self.next_id()
        self.seats[sid] = [x1, y1, x2, y2]
        warn = self.overlapping(sid)
        self.message = f"added {sid}" + (f"  (WARNING: overlaps {', '.join(warn)})" if warn else "")

    def _delete_at(self, x, y):
        # 여러 개가 겹쳐 있으면 가장 나중에 그린 것부터 삭제
        for sid in reversed(list(self.seats.keys())):
            x1, y1, x2, y2 = self.seats[sid]
            if x1 <= x <= x2 and y1 <= y <= y2:
                del self.seats[sid]
                self.message = f"deleted {sid}"
                return
        self.message = "nothing to delete here"

    def undo(self):
        if self.seats:
            sid = list(self.seats.keys())[-1]
            del self.seats[sid]
            self.message = f"undo {sid}"

    def rename_last(self, new_id):
        if not self.seats or not new_id:
            return
        if new_id in self.seats:
            self.message = f"'{new_id}' already exists"
            return
        last = list(self.seats.keys())[-1]
        self.seats[new_id] = self.seats.pop(last)
        self.message = f"renamed {last} -> {new_id}"

    # ---- 검사 ----
    def overlapping(self, sid):
        """sid 와 겹치는 다른 좌석 이름 목록."""
        out = []
        for other, box in self.seats.items():
            if other != sid and overlap_ratio_between(self.seats[sid], box) >= OVERLAP_WARN:
                out.append(other)
        return out

    def all_overlaps(self):
        pairs, ids = [], list(self.seats.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                r = overlap_ratio_between(self.seats[ids[i]], self.seats[ids[j]])
                if r >= OVERLAP_WARN:
                    pairs.append((ids[i], ids[j], r))
        return pairs

    # ---- 저장 ----
    def save(self, path):
        data = {
            "camera_id": self.camera_id,
            "frame_size": [self.w, self.h],
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seats": self.seats,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        pairs = self.all_overlaps()
        msg = f"saved {len(self.seats)} seats -> {path}"
        if pairs:
            msg += f"  (WARNING: {len(pairs)} overlapping pair(s))"
        self.message = msg
        return msg

    # ---- 그리기 ----
    def render(self):
        img = self.frame.copy()
        bad = {s for a, b, _ in self.all_overlaps() for s in (a, b)}
        for sid, (x1, y1, x2, y2) in self.seats.items():
            color = (0, 0, 255) if sid in bad else (0, 220, 0)
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(img, sid, (x1 + 4, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, color, 2, cv2.LINE_AA)
        if self.drawing:
            cv2.rectangle(img, self.p1, self.p2, (0, 255, 255), 2)
            cv2.putText(img, self.next_id(), (self.p1[0] + 4, self.p1[1] + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)

        # 상단 안내 바
        cv2.rectangle(img, (0, 0), (self.w, 54), (0, 0, 0), -1)
        cv2.putText(img, "drag: draw | right-click: delete | r: rename last | z: undo | n: next frame | s: save | q: quit",
                    (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(img, f"seats: {len(self.seats)}   next: {self.next_id()}   {self.message}",
                    (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
        return img


# ------------------------------------------------------------------
# 입력 소스 처리
# ------------------------------------------------------------------
def open_capture(source):
    """영상 파일 / 웹캠 번호 / 주소를 연다. 열리지 않으면 None.
    윈도우 웹캠은 기본 방식(MSMF)이 실패하는 경우가 많아 DSHOW 방식을 먼저 시도한다."""
    is_cam = isinstance(source, str) and source.isdigit()
    src = int(source) if is_cam else source
    backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if (is_cam and sys.platform.startswith("win")) else [cv2.CAP_ANY]
    for be in backends:
        cap = cv2.VideoCapture(src, be)
        if cap.isOpened():
            return cap
        cap.release()
    return None


def camera_help(source):
    """카메라가 열리지 않을 때 보여 줄 안내 문구 (열리는 다른 번호도 찾아 줌)."""
    found = []
    for i in range(4):
        c = open_capture(str(i))
        if c is not None:
            found.append(i)
            c.release()
    lines = [f"[오류] 카메라/영상 '{source}' 을(를) 열 수 없습니다.",
             "  1) 다른 프로그램(줌, 카카오톡, 윈도우 '카메라' 앱, 브라우저 탭)이 웹캠을 쓰고 있지 않은지 확인하세요.",
             "  2) 윈도우 설정 > 개인 정보 및 보안 > 카메라 에서 '카메라 액세스'와",
             "     '데스크톱 앱이 카메라에 액세스하도록 허용'이 켜져 있는지 확인하세요.",
             "  3) 웹캠이 여러 개면 번호를 바꿔 보세요 (--source 1, --source 2).",
             "  4) USB 웹캠이면 다른 USB 포트에 꽂아 보세요."]
    lines.append(f"  -> 지금 열리는 카메라 번호: {found}" if found else "  -> 열리는 카메라가 하나도 없습니다 (연결/권한 문제).")
    return "\n".join(lines)


def open_source(source):
    """(frame, capture 또는 None) 반환. 이미지 파일이면 capture 는 None."""
    if os.path.isfile(source):
        ext = os.path.splitext(source)[1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            frame = cv2.imread(source)
            if frame is None:
                raise FileNotFoundError(f"이미지를 열 수 없습니다: {source}")
            return frame, None
    cap = open_capture(source)
    if cap is None:
        raise RuntimeError(camera_help(source))
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError(f"카메라는 열렸지만 화면을 읽지 못했습니다: {source}\n"
                           "  (다른 프로그램이 사용 중이거나 카메라 권한이 꺼져 있을 수 있습니다)")
    return frame, cap


def advance(cap, is_file):
    """다음 프레임. 영상 파일이면 약 1초(fps 프레임) 건너뛰고, 카메라면 최신 프레임을 가져온다."""
    if cap is None:
        return None
    if is_file:
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
        pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos + fps)
    ok, frame = cap.read()
    return frame if ok else None


def main():
    ap = argparse.ArgumentParser(description="좌석 ROI 설정 도구")
    ap.add_argument("--source", required=True, help="이미지/영상 파일, 웹캠 번호(0), 또는 RTSP URL")
    ap.add_argument("--prefix", default="A-", help="좌석 번호 접두어 (예: 4-  ->  4-01, 4-02 ...). 층 번호로 시작해야 서버에 등록됩니다")
    ap.add_argument("--camera-id", default="", help="카메라 이름 (예: 4F-cam1)")
    ap.add_argument("--output", default="seats.json", help="저장 파일 경로")
    ap.add_argument("--load", default=None, help="기존 seats.json 을 불러와 이어서 편집")
    args = ap.parse_args()

    frame, cap = open_source(args.source)
    is_file = os.path.isfile(args.source)

    seats, camera_id = None, args.camera_id
    if args.load:
        seats, saved_size, saved_cam = load_seats(args.load)
        camera_id = camera_id or saved_cam
        h, w = frame.shape[:2]
        if saved_size and tuple(saved_size) != (w, h):
            print(f"[경고] 저장된 해상도 {saved_size} 와 현재 화면 {(w, h)} 이 다릅니다. "
                  f"좌표가 어긋날 수 있으니 같은 해상도의 영상을 사용하세요.")

    editor = SeatEditor(frame, prefix=args.prefix, camera_id=camera_id, seats=seats)

    win = "ROI Setup"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, min(editor.w, 1280), int(min(editor.w, 1280) * editor.h / editor.w))
    cv2.setMouseCallback(win, lambda ev, x, y, fl, pa: editor.on_mouse(ev, x, y))

    print("좌석 영역을 마우스로 드래그해서 그리세요. (s: 저장 / q: 종료)")
    while True:
        cv2.imshow(win, editor.render())
        key = cv2.waitKey(20) & 0xFF
        if key == ord("s"):
            print(editor.save(args.output))
        elif key == ord("z"):
            editor.undo()
        elif key == ord("r"):
            new_id = input("마지막 좌석의 새 이름 (예: 4-창가1): ").strip()
            editor.rename_last(new_id)
        elif key == ord("n"):
            nxt = advance(cap, is_file)
            if nxt is not None and nxt.shape[:2] == (editor.h, editor.w):
                editor.frame = nxt
            else:
                editor.message = "no more frames" if cap is not None else "single image"
        elif key == ord("q"):
            break

    cv2.destroyAllWindows()
    if cap is not None:
        cap.release()
    if editor.seats:
        if input("종료합니다. 저장할까요? (y/n): ").strip().lower() == "y":
            print(editor.save(args.output))


if __name__ == "__main__":
    main()
