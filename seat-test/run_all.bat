@echo off
cd /d "%~dp0"
if not exist library.db python setup_db.py --demo
start "server" cmd /k uvicorn main:app --port 8000
timeout /t 3 /nobreak >nul
start "detector" cmd /k python seat_detector.py --person-model models/person_seat.pt --item-model models/item_seat.pt --person-classes "Sit Down" --seats seats.json --source 2 --show --live
