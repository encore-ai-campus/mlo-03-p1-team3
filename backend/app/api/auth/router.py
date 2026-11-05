import secrets

from fastapi import APIRouter, Depends, Request, Response

from app.api.auth import service
from app.api.auth.schemas import KakaoLoginRequest, KakaoSignupRequest, LoginRequest, MeResponse, SignupRequest
from app.api.users.service import SignupData, signup
from app.core.config import KAKAO_SIGNUP_MINUTES
from app.core.deps import CurrentUser, current_user
from app.core.errors import AppError
from app.core.security import DEVICE_COOKIE, SESSION_COOKIE, clear_cookie, set_cookie, set_login_cookies
from app.core.time import utc_now

STATE_COOKIE = "podobank_kakao_state"
SIGNUP_COOKIE = "podobank_kakao_signup"
KAKAO_PATH = "/api/v1/auth/kakao"
KAKAO_COOKIE_SECONDS = KAKAO_SIGNUP_MINUTES * 60

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    info = service.client_info(request, request.cookies.get(DEVICE_COOKIE))
    token = service.login_with_password(request.app.state.engine, request, body.phone_number, body.password, info)
    set_login_cookies(response, token, info.device_id, request.app.state.settings)
    return {"status": "authenticated"}


@router.post("/signup")
def password_signup(body: SignupRequest, request: Request, response: Response):
    """자체 가입. 가입하면 바로 로그인 세션을 만든다."""
    engine = request.app.state.engine
    info = service.client_info(request, request.cookies.get(DEVICE_COOKIE))
    data = SignupData(**body.model_dump(exclude={"name"}))
    user_id = signup(engine, request.app.state.events, request, None, body.name, data)
    with engine.begin() as conn:
        token = service.start_session(conn, user_id, info.device_id, info.client, info.user_agent, utc_now())
    set_login_cookies(response, token, info.device_id, request.app.state.settings)
    return {"status": "authenticated"}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        service.end_session(request.app.state.engine, token, utc_now())
    clear_cookie(response, SESSION_COOKIE, request.app.state.settings)
    return {"status": "logged_out"}


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(current_user)):
    return MeResponse(id=user.id, name=user.name, role=user.role)


@router.post("/kakao/start")
def kakao_start(request: Request, response: Response):
    state = secrets.token_urlsafe(32)
    settings = request.app.state.settings
    set_cookie(response, STATE_COOKIE, state, KAKAO_COOKIE_SECONDS, settings, path=KAKAO_PATH)
    response.headers["Cache-Control"] = "no-store"
    return {"authorization_url": request.app.state.kakao.authorization_url(state)}


@router.post("/kakao/login")
def kakao_login(body: KakaoLoginRequest, request: Request, response: Response):
    settings = request.app.state.settings
    expected = request.cookies.get(STATE_COOKIE)
    if not expected or not secrets.compare_digest(expected, body.state):
        raise AppError(401, "kakao_state_invalid", "카카오 로그인 요청이 올바르지 않습니다")
    clear_cookie(response, STATE_COOKIE, settings, path=KAKAO_PATH)

    info = service.client_info(request, request.cookies.get(DEVICE_COOKIE))
    result = service.login_with_kakao(request.app.state.engine, request, request.app.state.kakao, body.code, info)
    if result.status == "authenticated":
        set_login_cookies(response, result.token, info.device_id, settings)
    else:
        set_cookie(response, SIGNUP_COOKIE, result.token, KAKAO_COOKIE_SECONDS, settings, path=KAKAO_PATH)
    return {"status": result.status}


@router.post("/kakao/signup")
def kakao_signup(body: KakaoSignupRequest, request: Request, response: Response):
    """카카오 인증 뒤 가입 화면. 전화번호·비밀번호를 정하므로 나중에 로컬 로그인도 된다."""
    settings = request.app.state.settings
    engine = request.app.state.engine
    pending = request.cookies.get(SIGNUP_COOKIE)
    subject, name = service.pending_kakao_signup(engine, pending)

    info = service.client_info(request, request.cookies.get(DEVICE_COOKIE))
    user_id = signup(engine, request.app.state.events, request, subject, name, SignupData(**body.model_dump()))
    token = service.finish_kakao_signup(engine, pending, user_id, info)
    clear_cookie(response, SIGNUP_COOKIE, settings, path=KAKAO_PATH)
    set_login_cookies(response, token, info.device_id, settings)
    return {"status": "authenticated"}
