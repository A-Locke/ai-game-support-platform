import pytest

from app import tools as tools_module
from app.config import settings


@pytest.fixture(autouse=True)
def configured_settings():
    """Point settings at a fake Chatwoot instance and reset the cached client per test."""
    settings.chatwoot_base_url = "http://chatwoot.test"
    settings.chatwoot_account_id = 1
    settings.chatwoot_api_access_token = "test-token"
    settings.enable_mutations = True
    tools_module.get_client.cache_clear()
    yield
    tools_module.get_client.cache_clear()
