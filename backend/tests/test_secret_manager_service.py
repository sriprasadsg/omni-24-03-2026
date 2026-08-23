import pytest
import os
import sys
from unittest.mock import MagicMock, patch

# Bootstrap sys.path to backend
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from secret_manager_service import SecretManagerService
import hvac.exceptions

# secret_manager_service imports VAULT_ADDR/VAULT_TOKEN by value at module
# load time (`from backend.config import VAULT_ADDR, VAULT_TOKEN`), so
# patching os.environ after that import has no effect on
# SecretManagerService.token — patch the module-level names it actually
# reads from instead.
@pytest.fixture(autouse=True)
def mock_vault_env_vars():
    with patch('secret_manager_service.VAULT_ADDR', 'http://mock-vault:8200'), \
         patch('secret_manager_service.VAULT_TOKEN', 'mock_token'):
        yield

@pytest.fixture
def mock_hvac_client():
    with patch('hvac.Client') as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.is_authenticated.return_value = True # Assume authenticated by default for tests
        yield mock_client_instance

@pytest.mark.asyncio
async def test_vault_client_connect_success(mock_hvac_client):
    """
    Test 1: Vault client successfully connects to VAULT_ADDR.
    """
    service = SecretManagerService()

    # Mock is_authenticated to return False initially to simulate a need to connect
    mock_hvac_client.is_authenticated.side_effect = [False, True]

    assert service.connect() is True
    mock_hvac_client.is_authenticated.assert_called() # Check if it tried to authenticate

@pytest.mark.asyncio
async def test_vault_client_connect_failure_no_token(mock_hvac_client):
    """
    Test connection failure when no token is provided and not authenticated.
    """
    # Temporarily remove VAULT_TOKEN for this test
    with patch('secret_manager_service.VAULT_TOKEN', ''):
        service = SecretManagerService()
        mock_hvac_client.is_authenticated.return_value = False
        with pytest.raises(hvac.exceptions.VaultError, match="Vault token not provided and client not authenticated."):
            service.connect()

@pytest.mark.asyncio
async def test_vault_client_connect_failure_bad_token(mock_hvac_client):
    """
    Test connection failure when token is provided but authentication fails.
    """
    service = SecretManagerService()
    mock_hvac_client.is_authenticated.side_effect = [False, False] # First call not auth, second call (after token set) also not auth

    with pytest.raises(hvac.exceptions.VaultError, match="Failed to authenticate with Vault using provided token."):
        service.connect()
    mock_hvac_client.is_authenticated.assert_called()


@pytest.mark.asyncio
async def test_vault_client_read_mock_secret_success(mock_hvac_client):
    """
    Test 2: Vault client can read a mock secret from a specified path.
    """
    service = SecretManagerService()
    mock_hvac_client.secrets.kv.v2.read_secret_version.return_value = {
        'data': {'data': {'username': 'testuser', 'password': 'testpassword'}}
    }

    secret = service.read_secret('secret/data/myapp/config')
    assert secret == {'username': 'testuser', 'password': 'testpassword'}
    mock_hvac_client.secrets.kv.v2.read_secret_version.assert_called_with(
        mount_point='secret', path='myapp/config'
    )

@pytest.mark.asyncio
async def test_vault_client_read_secret_no_data_prefix(mock_hvac_client):
    """
    Test reading secret from path without 'data/' prefix.
    """
    service = SecretManagerService()
    mock_hvac_client.secrets.kv.v2.read_secret_version.return_value = {
        'data': {'data': {'key': 'value'}}
    }
    secret = service.read_secret('secret/myapp/config')
    assert secret == {'key': 'value'}
    mock_hvac_client.secrets.kv.v2.read_secret_version.assert_called_with(
        mount_point='secret', path='myapp/config'
    )

@pytest.mark.asyncio
async def test_vault_client_read_secret_connection_error(mock_hvac_client):
    """
    Test 3: Handles connection errors gracefully during secret read.
    """
    service = SecretManagerService()
    # Always unauthenticated, however many times connect()/read_secret() call
    # it. A fixed-length side_effect list here previously raced against the
    # real call count and StopIteration'd once VAULT_TOKEN mocking actually
    # worked (see mock_vault_env_vars).
    mock_hvac_client.is_authenticated.return_value = False

    with pytest.raises(hvac.exceptions.VaultError, match="Failed to authenticate with Vault using provided token."):
        service.read_secret('secret/data/myapp/config')

@pytest.mark.asyncio
async def test_vault_client_read_secret_vault_error(mock_hvac_client):
    """
    Test handling of specific Vault errors during secret read.
    """
    service = SecretManagerService()
    mock_hvac_client.secrets.kv.v2.read_secret_version.side_effect = hvac.exceptions.VaultError("Permission denied")

    with pytest.raises(hvac.exceptions.VaultError, match="Error reading secret from Vault at path 'secret/data/myapp/config': Permission denied"):
        service.read_secret('secret/data/myapp/config')

@pytest.mark.asyncio
async def test_vault_client_read_secret_invalid_path(mock_hvac_client):
    """
    Test handling of invalid Vault path format. read_secret only validates
    that the path contains a '/' (mount_point/path) — 'myapp/config' is
    actually well-formed under that rule, so use a path with no separator
    at all to trigger the real ValueError.
    """
    service = SecretManagerService()
    with pytest.raises(ValueError, match="Invalid Vault path format: myapp_config_no_slash. Expected 'mount_point/path'."):
        service.read_secret('myapp_config_no_slash')

@pytest.mark.asyncio
async def test_vault_client_write_secret_success(mock_hvac_client):
    """
    Test writing a secret to Vault.
    """
    service = SecretManagerService()
    service.write_secret('secret/data/myapp/new_secret', {'api_key': 'abc123xyz'})
    mock_hvac_client.secrets.kv.v2.create_or_update_secret.assert_called_with(
        mount_point='secret', path='myapp/new_secret', secret={'api_key': 'abc123xyz'}
    )

@pytest.mark.asyncio
async def test_vault_client_write_secret_vault_error(mock_hvac_client):
    """
    Test handling of Vault errors during secret write.
    """
    service = SecretManagerService()
    mock_hvac_client.secrets.kv.v2.create_or_update_secret.side_effect = hvac.exceptions.VaultError("Write permission denied")

    with pytest.raises(hvac.exceptions.VaultError, match="Error writing secret to Vault at path 'secret/data/myapp/new_secret': Write permission denied"):
        service.write_secret('secret/data/myapp/new_secret', {'api_key': 'abc123xyz'})
