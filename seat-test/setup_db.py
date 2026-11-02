"""
setup_db.py  -  DB 만들기 / 좌석 등록 도구
==========================================

사용법 (seat-test 폴더에서)
---------------------------
python setup_db.py --demo
    시험용 좌석 등록: 4층 4석(4-01~04), 5층 6석(5-01~06), 6층 4석(6-01~04)   <- 프론트의 임시 데이터와 같은 구성

python setup_db.py --floor 4 --seats seats.json
    roi_setup.py 로 만든 seats.json 의 좌석을 4층으로 등록 (좌석 이름이 '4-01' 형식이어야 함)

python setup_db.py --list
    지금 등록된 좌석과 상태 보기

python setup_db.py --reset --demo
    기존 library.db 를 백업(삭제하지 않음)하고 새로 만든 뒤 등록

여러 번 실행해도 안전합니다 (이미 있는 좌석은 건드리지 않음).
"""

import argparse
import json
import sys

import db

DEMO = {4: 4, 5: 6, 6: 4}      # 층: 좌석 수


def read_seat_ids(path):
    """seats.json 에서 좌석 이름만 읽는다 (opencv 가 없는 컴퓨터에서도 동작하도록 json 으로 직접 읽음)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    seats = data["seats"] if isinstance(data, dict) and "seats" in data else data
    return list(seats)


def main(argv=None):
    ap = argparse.ArgumentParser(description="DB 만들기 / 좌석 등록")
    ap.add_argument("--db", default=db.DB_PATH, help="DB 파일 (기본 library.db)")
    ap.add_argument("--demo", action="store_true", help="시험용 좌석 등록 (4층 4석, 5층 6석, 6층 4석)")
    ap.add_argument("--floor", type=int, help="seats.json 의 좌석을 등록할 층 (예: 4)")
    ap.add_argument("--seats", default="seats.json", help="좌석 파일 (기본 seats.json)")
    ap.add_argument("--reset", action="store_true", help="기존 DB 를 백업하고 새로 시작")
    ap.add_argument("--list", action="store_true", help="등록된 좌석 목록 보기")
    args = ap.parse_args(argv)

    if args.reset:
        backup = db.backup_db(args.db)
        print(f"기존 DB 를 {backup} 로 옮겼습니다." if backup else "기존 DB 가 없어 새로 만듭니다.")

    db.init_db(args.db)

    try:
        if args.demo:
            for floor, n in DEMO.items():
                db.upsert_seats(floor, [f"{floor}-{i:02d}" for i in range(1, n + 1)], args.db)
            print("시험용 좌석을 등록했습니다: 4층 4석, 5층 6석, 6층 4석")

        if args.floor is not None:
            ids = read_seat_ids(args.seats)
            db.upsert_seats(args.floor, ids, args.db)
            print(f"{args.seats} 의 좌석 {len(ids)}개를 {args.floor}층으로 등록했습니다: {', '.join(ids)}")
    except ValueError as e:
        sys.exit(f"[오류] {e}\n  roi_setup.py 를 실행할 때 --prefix 4-  처럼 '<층>-' 로 시작하게 만들어야 합니다.")
    except (OSError, KeyError, json.JSONDecodeError) as e:
        sys.exit(f"[오류] {args.seats} 을(를) 읽지 못했습니다: {e}")

    if args.list or not (args.demo or args.floor is not None or args.reset):
        seats = db.get_all_seats(args.db)
        if not seats:
            print("등록된 좌석이 없습니다. 'python setup_db.py --demo' 로 시험용 좌석을 등록하세요.")
        for s in seats:
            print(f"  {s['floor']}층  {s['seat_id']:<6} {s['status']}")
        print(f"총 {len(seats)}석")


if __name__ == "__main__":
    main()
