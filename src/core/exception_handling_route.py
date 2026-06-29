import logging
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from src.core.base_exception import (
    AppError,
    AppTypeError,
    AppValidationError,
    AuthenticationInvalidScopeError,
    AuthenticationInvalidTokenError,
    AuthenticationTokenExpiredError,
    AuthenticationValidationError,
    CeleryKeyIndexIncrementError,
    ClientMethodMissingError,
    CrudIntegrityError,
    EmptyError,
    InstanceError,
    PermissionError,
    RateLimitExceededError,
    RedisClientCreationError,
)
from src.schemas.error import ErrorDetailSchema, ErrorResponseSchema

logger = logging.getLogger(__name__)


class ExceptionHandlingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            try:
                return await original_handler(request)
            except (
                AuthenticationInvalidTokenError,
                AuthenticationTokenExpiredError,
                AuthenticationValidationError,
            ) as exc:
                return JSONResponse(
                    status_code=401,
                    content=ExceptionHandlingRoute._error_payload(
                        "AUTH_ERROR", str(exc)
                    ),
                )
            except PermissionError as exc:
                return JSONResponse(
                    status_code=403,
                    content=ExceptionHandlingRoute._error_payload(
                        "AUTH_PERMISSION_ERROR", str(exc)
                    ),
                )
            except AuthenticationInvalidScopeError as exc:
                return JSONResponse(
                    status_code=403,
                    content=ExceptionHandlingRoute._error_payload(
                        "AUTH_INVALID_SCOPE", str(exc)
                    ),
                )
            except RateLimitExceededError as exc:
                return JSONResponse(
                    status_code=429,
                    content=ExceptionHandlingRoute._error_payload(
                        "RATE_LIMIT_EXCEEDED", str(exc)
                    ),
                )
            except CrudIntegrityError as exc:
                return JSONResponse(
                    status_code=500,
                    content=ExceptionHandlingRoute._error_payload(
                        "CRUD_INTEGRITY_ERROR", str(exc)
                    ),
                )
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content=ExceptionHandlingRoute._error_payload(
                        "REQUEST_VALIDATION_ERROR", str(exc)
                    ),
                )
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content=ExceptionHandlingRoute._error_payload(
                        "HTTP_ERROR", str(exc.detail)
                    ),
                )
            except httpx.HTTPStatusError as exc:
                upstream_status = exc.response.status_code
                mapped_status = ExceptionHandlingRoute._map_upstream_status(
                    upstream_status
                )
                return JSONResponse(
                    status_code=mapped_status,
                    content=ExceptionHandlingRoute._error_payload(
                        "UPSTREAM_HTTP_ERROR",
                        f"Upstream returned HTTP {upstream_status}",
                    ),
                )
            except httpx.RequestError as exc:
                return JSONResponse(
                    status_code=502,
                    content=ExceptionHandlingRoute._error_payload(
                        "UPSTREAM_REQUEST_ERROR",
                        f"Failed to reach upstream service: {str(exc)}",
                    ),
                )
            except CrudIntegrityError as exc:
                return JSONResponse(
                    status_code=409,
                    content=ExceptionHandlingRoute._error_payload(
                        "CRUD_INTEGRITY_ERROR", str(exc)
                    ),
                )
            except ClientMethodMissingError as exc:
                return JSONResponse(
                    status_code=400,
                    content=ExceptionHandlingRoute._error_payload(
                        "CLIENT_METHOD_MISSING_ERROR", str(exc)
                    ),
                )
            except (AppValidationError, AppTypeError, InstanceError, EmptyError) as exc:
                return JSONResponse(
                    status_code=400,
                    content=ExceptionHandlingRoute._error_payload(
                        "VALIDATION_ERROR", str(exc)
                    ),
                )
            except (
                RedisClientCreationError,
                CeleryKeyIndexIncrementError,
            ) as exc:
                return JSONResponse(
                    status_code=500,
                    content=ExceptionHandlingRoute._error_payload(
                        "INTEGRATION_ERROR", str(exc)
                    ),
                )
            except RedisClientCreationError as exc:
                return JSONResponse(
                    status_code=502,
                    content=ExceptionHandlingRoute._error_payload(
                        "REDIS_CLIENT_CREATION_ERROR", str(exc)
                    ),
                )
            except ValueError as exc:
                return JSONResponse(
                    status_code=400,
                    content=ExceptionHandlingRoute._error_payload(
                        "VALIDATION_ERROR", str(exc)
                    ),
                )
            except AppError as exc:
                return JSONResponse(
                    status_code=400,
                    content=ExceptionHandlingRoute._error_payload(
                        "APPLICATION_ERROR", str(exc)
                    ),
                )
            except Exception as exc:
                logger.exception(
                    "Unhandled exception in route %s %s",
                    request.method,
                    request.url.path,
                )
                return JSONResponse(
                    status_code=500,
                    content=ExceptionHandlingRoute._error_payload(
                        "INTERNAL_SERVER_ERROR",
                        f"Unexpected internal server error: {str(exc)}",
                    ),
                )

        return custom_route_handler

    @staticmethod
    def _error_payload(code: str, message: str) -> dict[str, Any]:
        payload = ErrorResponseSchema(
            error=ErrorDetailSchema(code=code, message=message),
        )
        return payload.model_dump()

    @staticmethod
    def _map_upstream_status(status_code: int) -> int:
        if status_code == 429:
            return 429
        if status_code in (401, 403, 404):
            return status_code
        if 500 <= status_code <= 599:
            return 502
        if 400 <= status_code <= 499:
            return 400
        return 502
