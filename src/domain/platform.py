_PROFILE_URL_MAX_LENGTH = 500


def validate_platform_specific_settings(settings: dict) -> dict:
    if "profile_url" not in settings:
        return settings

    profile_url = settings.get("profile_url")
    if profile_url is None:
        return {key: value for key, value in settings.items() if key != "profile_url"}

    if not isinstance(profile_url, str):
        raise ValueError("profile_url must be a string")

    normalized = profile_url.strip()
    if not normalized:
        raise ValueError("profile_url must not be empty")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("profile_url must start with http:// or https://")
    if len(normalized) > _PROFILE_URL_MAX_LENGTH:
        raise ValueError("profile_url is too long")

    validated = dict(settings)
    validated["profile_url"] = normalized
    return validated
