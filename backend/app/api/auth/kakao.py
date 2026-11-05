from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class KakaoProfile:
    subject: str
    name: str


class KakaoAuthError(Exception):
    """카카오가 코드를 거절함 (잘못된 코드, 만료)."""


class KakaoUnavailableError(Exception):
    """카카오 서버에 연결할 수 없음."""


class KakaoProvider(Protocol):
    def authorization_url(self, state: str) -> str: ...

    def fetch_profile(self, code: str) -> KakaoProfile: ...


class HttpKakaoProvider:
    def __init__(self, settings: Settings):
        self._settings = settings

    def authorization_url(self, state: str) -> str:
        query = urlencode({"client_id": self._settings.kakao_client_id, "redirect_uri": self._settings.kakao_redirect_uri,
                           "response_type": "code", "state": state})
        return f"https://kauth.kakao.com/oauth/authorize?{query}"

    def fetch_profile(self, code: str) -> KakaoProfile:
        try:
            with httpx.Client(timeout=5) as client:
                token = client.post("https://kauth.kakao.com/oauth/token", data={
                    "grant_type": "authorization_code", "client_id": self._settings.kakao_client_id,
                    "client_secret": self._settings.kakao_client_secret,
                    "redirect_uri": self._settings.kakao_redirect_uri, "code": code,
                })
                if token.status_code in (400, 401):
                    raise KakaoAuthError(token.text)
                token.raise_for_status()
                me = client.get("https://kapi.kakao.com/v2/user/me",
                                headers={"Authorization": f"Bearer {token.json()['access_token']}"})
                me.raise_for_status()
        except httpx.HTTPError as exc:
            raise KakaoUnavailableError(str(exc)) from exc
        body = me.json()
        nickname = body.get("kakao_account", {}).get("profile", {}).get("nickname") or "포도 고객"
        return KakaoProfile(subject=str(body["id"]), name=nickname[:50])
