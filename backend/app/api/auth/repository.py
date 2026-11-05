from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


def find_by_phone(conn: Connection, phone: str):
    return conn.execute(
        text("SELECT id, password_hash, role, locked_until FROM users WHERE phone_number = :p"), {"p": phone}
    ).mappings().first()


def find_by_kakao_subject(conn: Connection, subject: str):
    # FOR UPDATE: 같은 기기 동시 카카오 로그인도 세션이 하나만 남게 사용자 행을 잠근다.
    return conn.execute(
        text("SELECT id, role, locked_until FROM users WHERE kakao_subject = :s FOR UPDATE"), {"s": subject}
    ).mappings().first()


def reset_expired_lock(conn: Connection, user_id: int, now: datetime) -> None:
    conn.execute(
        text("UPDATE users SET failed_login_count = 0, locked_until = NULL"
             " WHERE id = :id AND locked_until IS NOT NULL AND locked_until <= :now"),
        {"id": user_id, "now": now},
    )


def record_failure(conn: Connection, user_id: int, max_failures: int, lock_until: datetime) -> None:
    # MariaDB는 SET을 왼쪽부터 계산하므로 locked_until을 먼저 정한다.
    conn.execute(
        text("UPDATE users SET locked_until = IF(failed_login_count + 1 >= :max, :lock_until, locked_until),"
             " failed_login_count = failed_login_count + 1 WHERE id = :id"),
        {"id": user_id, "max": max_failures, "lock_until": lock_until},
    )


def record_success(conn: Connection, user_id: int) -> None:
    conn.execute(text("UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE id = :id"), {"id": user_id})


def end_device_sessions(conn: Connection, user_id: int, device_id: str, now: datetime) -> None:
    conn.execute(
        text("UPDATE sessions SET ended_at = :now, end_reason = 'replaced'"
             " WHERE user_id = :u AND device_id = :d AND ended_at IS NULL"),
        {"now": now, "u": user_id, "d": device_id},
    )


def insert_session(conn: Connection, token_hash: str, user_id: int, device_id: str, client: str,
                   user_agent: str | None, login_method: str, now: datetime) -> None:
    conn.execute(
        text("INSERT INTO sessions (token_hash, user_id, device_id, client, user_agent, login_method,"
             " created_at, last_seen_at) VALUES (:h, :u, :d, :c, :a, :m, :now, :now)"),
        {"h": token_hash, "u": user_id, "d": device_id, "c": client, "a": user_agent, "m": login_method, "now": now},
    )


def find_active_session(conn: Connection, token_hash: str):
    return conn.execute(
        text("SELECT s.id, s.created_at, s.last_seen_at, u.id AS user_id, u.role, u.name"
             " FROM sessions s JOIN users u ON u.id = s.user_id"
             " WHERE s.token_hash = :h AND s.ended_at IS NULL"),
        {"h": token_hash},
    ).mappings().first()


def end_session(conn: Connection, session_id: int, reason: str, now: datetime) -> None:
    conn.execute(
        text("UPDATE sessions SET ended_at = :now, end_reason = :r WHERE id = :id AND ended_at IS NULL"),
        {"now": now, "r": reason, "id": session_id},
    )


def touch_session(conn: Connection, session_id: int, now: datetime, stale_before: datetime) -> None:
    # 조건부 UPDATE라서 1분 안에 요청이 동시에 여러 개 와도 한 번만 쓴다.
    conn.execute(
        text("UPDATE sessions SET last_seen_at = :now WHERE id = :id AND last_seen_at <= :stale"),
        {"now": now, "id": session_id, "stale": stale_before},
    )


def insert_kakao_signup(conn: Connection, token_hash: str, subject: str, name: str, now: datetime,
                        expires_at: datetime) -> None:
    conn.execute(
        text("INSERT INTO kakao_signups (token_hash, kakao_subject, name, created_at, expires_at)"
             " VALUES (:h, :s, :n, :now, :exp)"),
        {"h": token_hash, "s": subject, "n": name, "now": now, "exp": expires_at},
    )


def find_kakao_signup(conn: Connection, token_hash: str, now: datetime):
    return conn.execute(
        text("SELECT kakao_subject, name FROM kakao_signups WHERE token_hash = :h AND expires_at > :now"),
        {"h": token_hash, "now": now},
    ).mappings().first()


def delete_kakao_signup(conn: Connection, token_hash: str) -> None:
    conn.execute(text("DELETE FROM kakao_signups WHERE token_hash = :h"), {"h": token_hash})
