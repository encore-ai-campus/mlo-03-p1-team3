import os
from dataclasses import dataclass

# 팀원과 다시 정할 수 있는 숫자
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_MINUTES = 5
SESSION_IDLE_MINUTES = 10
SESSION_MAX_MINUTES = 60
SESSION_TOUCH_SECONDS = 60
DEVICE_COOKIE_DAYS = 365
KAKAO_SIGNUP_MINUTES = 5
PASSWORD_MIN_LENGTH = 8
CASH_MAX_AMOUNT = 10_000_000
TRANSFER_MAX_AMOUNT = 10_000_000
TRANSFER_DAILY_LIMIT = 100_000_000
LOCK_WAIT_SECONDS = 3
DB_POOL_SIZE = 10
DB_MAX_OVERFLOW = 10
DB_POOL_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Settings:
    mariadb_url: str
    mongodb_url: str
    mongodb_db: str
    event_log_path: str = "./var/log/app.log"
    cookie_secure: bool = False
    instance_name: str = "api"
    kakao_client_id: str = ""
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mariadb_url=os.environ["MARIADB_URL"],
            mongodb_url=os.environ["MONGODB_URL"],
            mongodb_db=os.environ.get("MONGODB_DB", "podobank"),
            event_log_path=os.environ.get("EVENT_LOG_PATH", "./var/log/app.log"),
            cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
            instance_name=os.environ.get("INSTANCE_NAME", "api"),
            kakao_client_id=os.environ.get("KAKAO_CLIENT_ID", ""),
            kakao_client_secret=os.environ.get("KAKAO_CLIENT_SECRET", ""),
            kakao_redirect_uri=os.environ.get("KAKAO_REDIRECT_URI", ""),
        )
