import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Pure unit tests do not require database setup."""
    yield
