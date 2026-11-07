"""계정 생성 없이 Nginx를 통해 FastAPI·MariaDB·MongoDB 상태를 확인합니다.

실행: .venv/bin/locust -f locustfile.py --host http://192.168.219.191 --web-host 127.0.0.1
화면: http://127.0.0.1:8089
단계별 측정·보고서: .venv/bin/python loadtest/run.py (loadtest/README.md 참고)
"""

from locust import HttpUser, between, task


class BackendHealthUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # 로컬 프록시 환경변수의 영향을 받지 않고 VM으로 직접 요청합니다.
        self.client.trust_env = False

    @task
    def check_database_health(self):
        with self.client.get(
            "/api/v1/health", timeout=10, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"예상하지 않은 HTTP 상태: {response.status_code}")
                return
            try:
                health = response.json()
            except ValueError:
                response.failure("JSON 응답이 아닙니다")
                return
            if not isinstance(health, dict) or any(
                health.get(database) != "ok" for database in ("mariadb", "mongodb")
            ):
                response.failure("MariaDB 또는 MongoDB 상태가 정상이 아닙니다")
