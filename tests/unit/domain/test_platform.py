import pytest

from src.domain.platform import validate_platform_specific_settings


def test_validate_platform_specific_settings_passthrough_without_profile_url():
    settings = {"theme": "dark"}
    assert validate_platform_specific_settings(settings) is settings


def test_validate_platform_specific_settings_drops_null_profile_url():
    validated = validate_platform_specific_settings(
        {"profile_url": None, "theme": "dark"},
    )
    assert validated == {"theme": "dark"}


def test_validate_platform_specific_settings_accepts_profile_url():
    validated = validate_platform_specific_settings(
        {"profile_url": " https://youtube.com/@CelebSpill "},
    )
    assert validated["profile_url"] == "https://youtube.com/@CelebSpill"


def test_validate_platform_specific_settings_accepts_http_profile_url():
    validated = validate_platform_specific_settings(
        {"profile_url": "http://example.com/profile"},
    )
    assert validated["profile_url"] == "http://example.com/profile"


def test_validate_platform_specific_settings_rejects_non_string_profile_url():
    with pytest.raises(ValueError, match="must be a string"):
        validate_platform_specific_settings({"profile_url": 123})


def test_validate_platform_specific_settings_rejects_empty_profile_url():
    with pytest.raises(ValueError, match="must not be empty"):
        validate_platform_specific_settings({"profile_url": "   "})


def test_validate_platform_specific_settings_rejects_invalid_profile_url():
    with pytest.raises(ValueError, match="http"):
        validate_platform_specific_settings({"profile_url": "not-a-url"})


def test_validate_platform_specific_settings_rejects_too_long_profile_url():
    with pytest.raises(ValueError, match="too long"):
        validate_platform_specific_settings(
            {"profile_url": f"https://example.com/{'a' * 500}"},
        )
