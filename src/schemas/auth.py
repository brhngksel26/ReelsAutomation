from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = None
    last_name: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str | None
    last_name: str | None
    tier: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    is_verified: bool


class UserMeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    is_verified: bool
    profile: ProfileOut | None = None
