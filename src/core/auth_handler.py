from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi.security import HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError

from src.core.base_exception import (
    AuthenticationInvalidScopeError,
    AuthenticationInvalidTokenError,
    AuthenticationTokenExpiredError,
    AuthenticationValidationError,
)
from src.core.config import settings


class AuthHandler:
    security = HTTPBearer()
    secret = settings.JWT_ACCESS_SECRET_KEY

    @classmethod
    def get_password_hash(cls, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    @classmethod
    def encode_token(cls, email, scope, ttl):
        exp = datetime.now(timezone.utc) + timedelta(**ttl)
        try:
            payload = {
                "exp": exp,
                "iat": datetime.now(timezone.utc),
                "scope": scope,
                "sub": email,
            }
            return jwt.encode(
                payload, cls.secret, algorithm=settings.ENCRYPTION_ALGORITHM
            )
        except Exception as exception:
            raise AuthenticationValidationError(
                f"Could not validate credentials: {exception}"
            ) from exception

    @classmethod
    def decode_token(cls, token, scope):
        try:
            payload = jwt.decode(
                token, cls.secret, algorithms=[settings.ENCRYPTION_ALGORITHM]
            )
            if payload["scope"] != scope:
                raise AuthenticationInvalidScopeError(
                    f"Invalid scope for token: {payload['scope']}"
                )
            return payload["sub"]
        except ExpiredSignatureError as exception:
            raise AuthenticationTokenExpiredError(
                f"Token expired: {exception}"
            ) from exception
        except InvalidTokenError as exception:
            raise AuthenticationInvalidTokenError(
                f"Invalid access token: {exception}"
            ) from exception

    @classmethod
    def refresh_token(cls, refresh_token):
        email = cls.decode_token(refresh_token, "refresh_token")
        return cls.encode_token(email, "access_token", {"days": 0, "hours": 2})
