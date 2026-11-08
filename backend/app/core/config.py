import os
from dataclasses import dataclass
from pathlib import Path

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
DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 0
DB_POOL_TIMEOUT_SECONDS = 5
DB_POOL_RECYCLE_SECONDS = 1800


@dataclass(frozen=True)
class Settings:
    mariadb_url: str
    mongodb_url: str
    mongodb_db: str
    event_log_path: str = "./var/log/events.log"
    app_log_path: str = "./var/log/app.log"
    cookie_secure: bool = False
    instance_name: str = "api"
    kakao_client_id: str = ""
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = ""
    otel_traces_endpoint: str = ""
    otel_sample_ratio: float = 0.1

    def __post_init__(self):
        if not 0 <= self.otel_sample_ratio <= 1:
            raise ValueError("OTEL_SAMPLE_RATIO must be between 0 and 1")
        if Path(self.app_log_path).resolve() == Path(self.event_log_path).resolve():
            raise ValueError("APP_LOG_PATH and EVENT_LOG_PATH must be different")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mariadb_url=os.environ["MARIADB_URL"],
            mongodb_url=os.environ["MONGODB_URL"],
            mongodb_db=os.environ.get("MONGODB_DB", "podobank"),
            event_log_path=os.environ.get("EVENT_LOG_PATH", "./var/log/events.log"),
            app_log_path=os.environ.get("APP_LOG_PATH", "./var/log/app.log"),
            cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
            instance_name=os.environ.get("INSTANCE_NAME", "api"),
            kakao_client_id=os.environ.get("KAKAO_CLIENT_ID", ""),
            kakao_client_secret=os.environ.get("KAKAO_CLIENT_SECRET", ""),
            kakao_redirect_uri=os.environ.get("KAKAO_REDIRECT_URI", ""),
            otel_traces_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", ""),
            otel_sample_ratio=float(os.environ.get("OTEL_SAMPLE_RATIO", "0.1")),
        )
