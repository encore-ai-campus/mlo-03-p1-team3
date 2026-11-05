from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from app.api.users.service import SignupData, signup
from app.core.errors import AppError


def test_parallel_signup_same_phone(engine, sink):
    """같은 전화번호로 동시에 가입하면 한 명만 만들어지고 다른 쪽은 409가 된다."""
    data = SignupData(phone_number="01055556666", password="password123", birth_year=1990,
                      gender="female", marital_status="married", is_employed=False)

    def attempt(_):
        try:
            return signup(engine, sink, None, None, "이포도", data)
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))

    with engine.connect() as conn:
        users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        accounts = conn.execute(text("SELECT COUNT(*) FROM accounts")).scalar()
    assert (users, accounts) == (1, 1)
    assert [r for r in results if isinstance(r, str)] == ["phone_already_registered"]
    assert sum(isinstance(r, int) for r in results) == 1


def test_parallel_kakao_signup_same_subject(engine, sink):
    """같은 카카오 계정으로 동시에 가입하면 사용자는 한 명만 만들어진다."""
    data = SignupData(phone_number="01077778888", password="password123", birth_year=1990,
                      gender="female", marital_status="married", is_employed=False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: signup(engine, sink, None, "kakao-same", "이포도", data), range(2)))

    with engine.connect() as conn:
        users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    assert users == 1
    assert ids[0] == ids[1]
