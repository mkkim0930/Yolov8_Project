책갈피 - 도서관 1인석 좌석 서비스 (서버 + 탐지)
==============================================

폴더 구성 (한 폴더에 평평하게)
  main.py           FastAPI 서버            db.py          DB 규칙 (library.db 를 만들고 읽고 씀)
  setup_db.py       DB 생성 / 좌석 등록     seat_detector.py   웹캠 탐지 -> 서버로 전송
  roi_setup.py      좌석 영역(ROI) 지정     seats.json     좌석 영역 (샘플 포함)
  gen_vapid.py      푸시 알림 키 생성       test_db.py     DB 규칙 자동 시험
  test_webcam.py / test_image.py            카메라 / 사진 한 장 시험
  models/           person_seat.pt(사람), item_seat.pt(물건)
  frontend/         (선택) npm run build 결과를 넣으면 서버 하나로 화면까지 제공
  API.md            주고받는 JSON 정리

설치:  pip install -r requirements.txt

처음 한 번 (새 구조 DB 만들기)
  python setup_db.py --demo
    -> 4층 4석(4-01~), 5층 6석, 6층 4석 등록. 예전 library.db 가 있으면 자동 백업 후 새로 만듭니다.
  내 웹캠 좌석을 쓰려면 (좌석 이름이 '층-번호' 형식이어야 함):
    python roi_setup.py --source 0 --prefix 4- --output seats.json 
    python setup_db.py --floor 4 --seats seats.json
  ※ 예전 seats.json 의 이름(6F-01 등)은 '6-01' 처럼 바꾸거나 다시 만들어야 합니다.

실행
  1) 서버:   uvicorn main:app --port 8000
  2) 화면:   (nari-library-share 폴더) npm run dev  -> http://localhost:5173
  3) 탐지:   python seat_detector.py --person-model models/person_seat.pt --item-model models/item_seat.pt ^
                 --person-classes "Sit Down" --seats seats.json --source 0 --show --live
     또는 run_all.bat 더블클릭 (서버+탐지 창 동시에)

규칙
  상태: 사람 있음=inUse, 사람 없고 물건 있음=occupied, 둘 다 없음=available (기본값)
  점유 중(occupied)이 1시간 이어지면 분실물로 자동 등록 -> 관리자 확인 -> "수거 물품 안내"에 표시
  시연: SAKHWA_SECONDS=30 SAKHWA_CHECK_SEC=5 ADMIN_TOKEN=원하는값 으로 서버 실행

시험 (서버·카메라 없이)
  python test_db.py

보안 (내 컴퓨터에서만 쓸 때는 기본값으로 충분)
  외부에 공개하면: DETECTOR_KEY(탐지 인증), ADMIN_TOKEN, CORS_ORIGINS, DISABLE_DOCS=1 설정,
  vapid_private.pem / library.db / 토큰은 git 에 올리지 마세요. .pt 모델은 믿을 수 있는 것만 쓰세요.
