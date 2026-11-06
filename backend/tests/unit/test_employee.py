import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.security import verify_password
from app.db.employee import EmployeeConfig, EmployeeSetupError, ensure_employee, verify_credentials


@pytest.fixture
def employee_db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, phone_number TEXT UNIQUE, "
                          "password_hash TEXT, name TEXT, birth_year INTEGER, gender TEXT, "
                          "marital_status TEXT, is_employed BOOLEAN, role TEXT)"))
    yield engine
    engine.dispose()


def config(password="test-only-password"):
    return EmployeeConfig("01000000000", password, "테스트 직원")


def test_employee_created_with_hash_and_preserved_on_rerun(employee_db):
    assert ensure_employee(employee_db, config()) == "created"
    with employee_db.connect() as conn:
        before = dict(conn.execute(text("SELECT * FROM users")).mappings().one())
    assert before["role"] == "bank_employee"
    assert verify_password(before["password_hash"], config().password)
    assert ensure_employee(employee_db, config("different-password")) == "existing"
    with employee_db.connect() as conn:
        assert dict(conn.execute(text("SELECT * FROM users")).mappings().one()) == before


def test_customer_is_never_promoted(employee_db):
    ensure_employee(employee_db, config())
    with employee_db.begin() as conn:
        conn.execute(text("UPDATE users SET role='customer'"))
    with pytest.raises(EmployeeSetupError, match="employee_phone_conflicts_with_customer"):
        ensure_employee(employee_db, config())
    with employee_db.connect() as conn:
        assert conn.execute(text("SELECT role FROM users")).scalar_one() == "customer"


@pytest.mark.parametrize("phone,password,name", [("not-a-phone-number", "long-password", "직원"),
    ("01000000000", "short", "직원"), ("01000000000", "long-password", " ")])
def test_invalid_configuration_does_not_expose_values(phone, password, name):
    with pytest.raises(EmployeeSetupError) as caught:
        EmployeeConfig(phone, password, name)
    assert password not in str(caught.value)
    assert phone not in str(caught.value)


def test_wrong_password_does_not_modify_existing_account(employee_db):
    ensure_employee(employee_db, config())
    with pytest.raises(EmployeeSetupError, match="employee_credentials_do_not_match_existing_account"):
        verify_credentials(employee_db, config("different-password"))
    verify_credentials(employee_db, config())


def test_private_env_parser_handles_quoted_values_and_check_hides_them(tmp_path):
    private_env = tmp_path / ".env"
    fake_password = "example-$-with#quotes'"
    private_env.write_text("IGNORED_KEY=unrelated\nEMPLOYEE_PHONE_NUMBER=01000000000\n"
                           f'EMPLOYEE_PASSWORD="{fake_password}"\nEMPLOYEE_NAME="Example Employee"\n')
    script = Path(__file__).resolve().parents[3] / "deploy/ansible/read-employee-env.py"
    result = subprocess.run([sys.executable, str(script), str(private_env)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert json.loads(result.stdout)["EMPLOYEE_PASSWORD"] == fake_password
    checked = subprocess.run([sys.executable, str(script), str(private_env), "--check"], capture_output=True, text=True, check=False)
    assert checked.returncode == 0
    assert fake_password not in checked.stdout + checked.stderr
