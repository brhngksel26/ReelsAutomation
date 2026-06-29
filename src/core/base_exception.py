class AppError(Exception):
    pass


class AuthenticationError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class AuthenticationValidationError(AuthenticationError):
    def __init__(self, message: str):
        super().__init__(message)


class AuthenticationInvalidTokenError(AuthenticationError):
    def __init__(self, message: str):
        super().__init__(message)


class AuthenticationTokenExpiredError(AuthenticationError):
    def __init__(self, message: str):
        super().__init__(message)


class AuthenticationInvalidScopeError(AuthenticationError):
    def __init__(self, message: str):
        super().__init__(message)


class CrudIntegrityError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class RedisClientCreationError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class CeleryKeyIndexIncrementError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class RateLimitExceededError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class RateLimitExhausted(AppError):
    """Outbound CH quota bucket full; caller should retry after retry_after seconds."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(
            f"Companies House rate limit bucket exhausted; retry after {retry_after:.1f}s"
        )


class ClientMethodMissingError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class InstanceError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class AppTypeError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class EmptyError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class AppValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class PermissionError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class LLMError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class LLMProviderUnavailableError(LLMError):
    def __init__(self, message: str):
        super().__init__(message)


class LLMOutputParseError(LLMError):
    def __init__(self, message: str):
        super().__init__(message)


class LLMRateLimitError(LLMError):
    def __init__(self, message: str):
        super().__init__(message)


class MoneyPrinterError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class MoneyPrinterRequestError(MoneyPrinterError):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class MoneyPrinterTaskError(MoneyPrinterError):
    def __init__(self, message: str, task_id: str | None = None):
        self.task_id = task_id
        super().__init__(message)


class MoneyPrinterTimeoutError(MoneyPrinterError):
    def __init__(self, message: str, task_id: str | None = None):
        self.task_id = task_id
        super().__init__(message)


class PlatformError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class PlatformRequestError(PlatformError):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class PlatformAuthError(PlatformError):
    def __init__(self, message: str):
        super().__init__(message)


class PlatformUploadError(PlatformError):
    def __init__(self, message: str):
        super().__init__(message)


class PlatformRateLimitError(PlatformError):
    def __init__(self, message: str, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(message)
