from fastapi import FastAPI

from app.api.accounts.router import router as accounts_router
from app.api.admin.router import router as admin_router
from app.api.auth.kakao import HttpKakaoProvider
from app.api.auth.router import router as auth_router
from app.api.cards.router import router as cards_router
from app.api.events.service import make_sink
from app.api.health.router import router as health_router
from app.api.loans.router import router as loans_router
from app.api.transactions.router import router as transactions_router
from app.api.transfers.router import router as transfers_router
from app.core.config import Settings
from app.core.errors import install_error_handlers
from app.db.mariadb import make_engine
from app.observability.application_log import ApplicationLog, install_application_log
from app.observability.metrics import install_metrics
from app.observability.request_id import install_request_id

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="PodoBank API")
    app.state.settings = settings
    app.state.engine = make_engine(settings.mariadb_url)
    application_log = ApplicationLog(settings.app_log_path, settings.instance_name)
    app.state.events = make_sink(settings, application_log)
    app.state.mongo = app.state.events.mongo_db
    app.state.kakao = HttpKakaoProvider(settings)
    install_request_id(app)
    install_application_log(app, application_log)
    install_error_handlers(app)
    install_metrics(app)

    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(accounts_router, prefix=API_PREFIX)
    app.include_router(transactions_router, prefix=API_PREFIX)
    app.include_router(transfers_router, prefix=API_PREFIX)
    app.include_router(cards_router, prefix=API_PREFIX)
    app.include_router(loans_router, prefix=API_PREFIX)
    app.include_router(admin_router, prefix=API_PREFIX)
    return app
