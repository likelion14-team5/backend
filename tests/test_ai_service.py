from app.core.config import Settings
from app.services.ai_service import AiService


def test_client_uses_configured_max_retries() -> None:
    settings = Settings(openai_api_key="sk-test", openai_max_retries=5)
    service = AiService(settings=settings)

    client = service._client_or_error("AI_TEST_FAILED")

    assert client.max_retries == 5


def test_client_defaults_to_three_retries() -> None:
    settings = Settings(openai_api_key="sk-test")
    service = AiService(settings=settings)

    client = service._client_or_error("AI_TEST_FAILED")

    assert client.max_retries == 3
