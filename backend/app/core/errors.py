from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability.request_id import get_request_id

HTTP_CODES = {
    400: ("bad_request", "잘못된 요청입니다"),
    401: ("authentication_required", "로그인이 필요합니다"),
    403: ("forbidden", "권한이 없습니다"),
    404: ("not_found", "요청한 주소를 찾을 수 없습니다"),
    405: ("method_not_allowed", "허용되지 않은 요청 방식입니다"),
}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict[str, str] | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields


def error_response(request: Request, status: int, code: str, message: str, fields=None) -> JSONResponse:
    request_id = get_request_id(request)
    body = {"code": code, "message": message, "request_id": request_id}
    if fields:
        body["fields"] = fields
    return JSONResponse(status_code=status, content=body, headers={"X-Request-ID": request_id})


async def _app_error(request: Request, exc: AppError):
    return error_response(request, exc.status, exc.code, exc.message, exc.fields)


async def _validation_error(request: Request, exc: RequestValidationError):
    fields = {}
    for error in exc.errors():
        loc = [str(part) for part in error["loc"] if part not in ("body", "query", "path", "header")]
        fields[".".join(loc) or "body"] = "형식이 올바르지 않습니다"
    return error_response(request, 422, "validation_error", "입력값을 확인해 주세요", fields)


async def _http_error(request: Request, exc: StarletteHTTPException):
    code, message = HTTP_CODES.get(exc.status_code, ("http_error", "요청을 처리할 수 없습니다"))
    return error_response(request, exc.status_code, code, message)


async def _db_error(request: Request, exc: Exception):
    # 로그인·조회·권한 확인처럼 translate_db_errors 밖에서 난 DB 오류도 500 대신 409/503으로 돌려준다.
    from app.db.mariadb import to_app_error

    error = to_app_error(exc)
    return error_response(request, error.status, error.code, error.message)


async def _unhandled(request: Request, exc: Exception):
    return error_response(request, 500, "internal_error", "일시적인 오류가 발생했습니다")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(OperationalError, _db_error)
    app.add_exception_handler(PoolTimeoutError, _db_error)
    app.add_exception_handler(Exception, _unhandled)
