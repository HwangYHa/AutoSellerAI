"""AutoSellerAI 운영용 비밀값 생성기.

사용:
    python scripts/generate_secrets.py

출력값을 로컬 .env에만 복사하고 GitHub에는 커밋하지 마세요.
"""
from secrets import token_urlsafe


def main() -> None:
    print(f"SECRET_KEY={token_urlsafe(48)}")
    print(f"TRACKING_HASH_SALT={token_urlsafe(48)}")
    print(f"THREADS_VERIFY_TOKEN={token_urlsafe(32)}")
    try:
        from cryptography.fernet import Fernet
        print(f"THREADS_TOKEN_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    except Exception:
        print("# cryptography 설치 후 THREADS_TOKEN_ENCRYPTION_KEY를 생성하세요.")


if __name__ == "__main__":
    main()
