from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import PASSWORD_MIN_LENGTH


class LoginRequest(BaseModel):
    phone_number: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=128)


class MeResponse(BaseModel):
    id: int
    name: str
    role: str


class KakaoLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=128)


class KakaoSignupRequest(BaseModel):
    """카카오 인증 뒤 가입 화면. 이름은 카카오 프로필에서 가져온다."""

    phone_number: str = Field(pattern=r"^01[0-9]{8,9}$")
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)
    birth_year: int
    gender: Literal["male", "female"]
    marital_status: Literal["single", "married"]
    is_employed: bool

    @field_validator("birth_year")
    @classmethod
    def _birth_year_range(cls, value: int) -> int:
        if not 1900 <= value <= date.today().year:
            raise ValueError("birth_year out of range")
        return value


class SignupRequest(KakaoSignupRequest):
    """자체 가입. 카카오 가입 항목에 이름을 더한다."""

    name: str = Field(max_length=50)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name is blank")
        return value
