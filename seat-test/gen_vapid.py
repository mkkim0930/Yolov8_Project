"""
gen_vapid.py - 웹 푸시용 VAPID 키 생성 (처음 1번만 실행)

python gen_vapid.py

 -> private_key.pem  : 서버만 보관 (절대 공개/업로드 금지)
 -> 화면에 출력되는 PUBLIC KEY : 서버의 VAPID_PUBLIC_KEY 환경 변수에 넣으면
                                   프론트엔드가 GET /vapid-public-key 로 받아 사용

서버 실행 전 환경 변수:
  VAPID_PRIVATE_FILE=private_key.pem
  VAPID_PUBLIC_KEY=<아래 출력값>
  VAPID_EMAIL=mailto:본인메일@example.com
"""
import base64
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

OUT = "private_key.pem"
if os.path.exists(OUT):
    sys.exit(f"{OUT} 가 이미 있습니다. 덮어쓰면 기존 알림 구독이 모두 무효가 되므로 중단합니다.")

key = ec.generate_private_key(ec.SECP256R1())
pem = key.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.TraditionalOpenSSL,
                        serialization.NoEncryption())
open(OUT, "wb").write(pem)

pub = key.public_key().public_bytes(serialization.Encoding.X962,
                                    serialization.PublicFormat.UncompressedPoint)
print(f"개인키 저장: {OUT}")
print("PUBLIC KEY :", base64.urlsafe_b64encode(pub).rstrip(b"=").decode())
