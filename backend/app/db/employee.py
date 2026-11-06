"""Prepare an employee from environment variables or private JSON on stdin."""
import argparse
import http.cookiejar
import json
import os
import re
import sys
from dataclasses import dataclass, field
from urllib.request import HTTPCookieProcessor, Request, build_opener

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import PASSWORD_MIN_LENGTH
from app.core.security import hash_password, verify_password


class EmployeeSetupError(Exception):
    pass


@dataclass(frozen=True)
class EmployeeConfig:
    phone: str = field(repr=False)
    password: str = field(repr=False)
    name: str = field(repr=False)

    def __post_init__(self):
        if not re.fullmatch(r"01[0-9]{8,9}", self.phone):
            raise EmployeeSetupError("invalid_employee_phone")
        if not PASSWORD_MIN_LENGTH <= len(self.password) <= 128:
            raise EmployeeSetupError("invalid_employee_password_length")
        if not self.name.strip() or len(self.name) > 50:
            raise EmployeeSetupError("invalid_employee_name")

    @classmethod
    def from_values(cls, values):
        try:
            return cls(*(values[key] for key in (
                "EMPLOYEE_PHONE_NUMBER", "EMPLOYEE_PASSWORD", "EMPLOYEE_NAME")))
        except (KeyError, TypeError):
            raise EmployeeSetupError("missing_employee_configuration") from None


def ensure_employee(engine: Engine, config: EmployeeConfig) -> str:
    def existing():
        with engine.connect() as conn:
            row = conn.execute(text("SELECT role FROM users WHERE phone_number=:p"),
                               {"p": config.phone}).scalar_one_or_none()
        if row is None:
            return False
        if row != "bank_employee":
            raise EmployeeSetupError("employee_phone_conflicts_with_customer")
        return True

    if existing():
        return "existing"
    password_hash = hash_password(config.password)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (phone_number,password_hash,name,birth_year,gender,marital_status,"
                "is_employed,role) VALUES (:p,:h,:n,1990,'female','single',TRUE,'bank_employee')"),
                {"p": config.phone, "h": password_hash, "n": config.name.strip()})
    except IntegrityError:
        if not existing():
            raise EmployeeSetupError("employee_insert_failed") from None
        return "existing"
    return "created"


def verify_credentials(engine: Engine, config: EmployeeConfig) -> None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT role,password_hash FROM users WHERE phone_number=:p"),
                           {"p": config.phone}).mappings().first()
    if not row or row["role"] != "bank_employee" or not verify_password(row["password_hash"], config.password):
        raise EmployeeSetupError("employee_credentials_do_not_match_existing_account")


def verify_http(base: str, config: EmployeeConfig) -> None:
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, body=None):
        req = Request(base.rstrip("/") + "/api/v1" + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=15) as response:
            if response.status != 200:
                raise EmployeeSetupError("employee_http_verification_failed")
            return json.load(response)

    try:
        call("/auth/login", {"phone_number": config.phone, "password": config.password})
        if call("/auth/me").get("role") != "bank_employee":
            raise EmployeeSetupError("employee_role_verification_failed")
        if not isinstance(call("/admin/loans/pending?limit=1"), list):
            raise EmployeeSetupError("employee_permission_verification_failed")
    finally:
        call("/auth/logout", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdin", action="store_true", help="Read private configuration as JSON from stdin")
    parser.add_argument("--verify-base-url", help="Only verify credentials and HTTP access; never approve a loan")
    args = parser.parse_args()
    engine = None
    try:
        from app.db.mariadb import make_engine
        config = EmployeeConfig.from_values(json.load(sys.stdin) if args.stdin else os.environ)
        engine = make_engine(os.environ["MARIADB_URL"])
        if args.verify_base_url:
            verify_credentials(engine, config)
            verify_http(args.verify_base_url, config)
            print(json.dumps({"status": "verified", "login": True, "employee_access": True, "logout": True}))
        else:
            print(json.dumps({"status": ensure_employee(engine, config)}))
    except EmployeeSetupError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    except json.JSONDecodeError:
        print(json.dumps({"error": "employee_configuration_json_invalid"}), file=sys.stderr)
        return 1
    except (SQLAlchemyError, OSError, ValueError, TypeError, KeyError) as error:
        # Database/HTTP/validation exceptions can contain private values.
        print(json.dumps({"error": "employee_setup_or_verification_failed", "kind": type(error).__name__}), file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
