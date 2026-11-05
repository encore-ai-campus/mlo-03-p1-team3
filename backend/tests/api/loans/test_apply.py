from sqlalchemy import text

from tests.conftest import login, recorded_events

APPLY = "/api/v1/loans/applications"


def apply(client, product="car", amount=30_000_000, term=60):
    return client.post(APPLY, json={"product_code": product, "amount": amount, "term_months": term})


def test_products_list(client, make_user):
    login(client, make_user())

    products = client.get("/api/v1/loans/products").json()

    assert [p["code"] for p in products] == ["car", "jeonse", "home"]
    car = products[0]
    assert "annual_rate_bp" not in car and car["max_amount"] == 50_000_000
    assert car["amount_step"] == 1_000_000 and car["term_options"] == [12, 24, 36, 48, 60, 120]


def test_apply_success_pending(client, make_user, engine):
    login(client, make_user())

    response = apply(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["monthly_installment"] == 500_000  # 3,000만 원 ÷ 60개월, 이자 없음
    with engine.connect() as conn:
        row = conn.execute(text("SELECT product_code, principal_amount, term_months, status"
                                " FROM loan_applications")).one()
    assert tuple(row) == ("car", 30_000_000, 60, "pending")
    event = recorded_events("loan_application")[0]
    assert event["properties"] == {"product_code": "car", "term_months": 60, "amount_band": "over_1m"}


def test_amount_out_of_range_422(client, make_user):
    login(client, make_user())

    assert apply(client, amount=51_000_000).json()["code"] == "loan_amount_out_of_range"
    assert apply(client, amount=0).json()["code"] == "loan_amount_out_of_range"


def test_amount_not_step_422(client, make_user):
    login(client, make_user())

    assert apply(client, amount=1_234_567).json()["code"] == "invalid_loan_amount"


def test_term_not_option_422(client, make_user):
    login(client, make_user())

    assert apply(client, term=37).json()["code"] == "invalid_loan_term"


def test_unknown_product_404(client, make_user):
    login(client, make_user())

    assert apply(client, product="boat").json()["code"] == "product_not_found"


def test_active_loan_409(client, make_user):
    login(client, make_user())
    apply(client)

    response = apply(client, product="home", amount=100_000_000, term=120)

    assert response.status_code == 409
    assert response.json()["code"] == "active_loan_exists"


def test_can_apply_again_after_rejection(client, make_user, engine):
    login(client, make_user())
    apply(client)
    with engine.begin() as conn:
        conn.execute(text("UPDATE loan_applications SET status = 'rejected'"))

    assert apply(client).status_code == 200


def test_my_loans(client, make_user):
    login(client, make_user())
    application_id = apply(client).json()["application_id"]

    loans = client.get("/api/v1/loans/me").json()

    assert loans == [{"application_id": application_id, "product_code": "car", "status": "pending",
                      "principal_amount": 30_000_000, "term_months": 60,
                      "monthly_installment": 500_000, "installments": []}]


def test_employee_cannot_apply_403(client, make_user):
    login(client, make_user(role="bank_employee"))

    assert apply(client).status_code == 403
