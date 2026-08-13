import pytest
from unittest.mock import patch, MagicMock
from backend.secret_manager_service import VaultService
import hvac

@patch('hvac.Client')
def test_vault_client_connect_success(mock_hvac_client):
    """Test that the Vault client initializes and connects successfully."""
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.return_value = True
    mock_hvac_client.return_value = mock_client_instance

    service = VaultService()
    assert service.client is not None
    assert service.client.is_authenticated()

@patch('hvac.Client')
def test_vault_client_connect_failure(mock_hvac_client):
    """Test that the Vault client handles connection errors gracefully."""
    mock_hvac_client.side_effect = hvac.exceptions.VaultDown

    with pytest.raises(hvac.exceptions.VaultDown):
        VaultService()

@patch('hvac.Client')
def test_read_secret_success(mock_hvac_client):
    """Test successfully reading a secret from Vault."""
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.return_value = True
    mock_client_instance.secrets.kv.v2.read_secret_version.return_value = {
        'data': {
            'data': {
                'key': 'value'
            }
        }
    }
    mock_hvac_client.return_value = mock_client_instance

    service = VaultService()
    secret = service.read_secret('secret/data/mock')
    assert secret == {'key': 'value'}
    service.client.secrets.kv.v2.read_secret_version.assert_called_with(mount_point='secret', path='mock')

@patch('hvac.Client')
def test_read_secret_not_found(mock_hvac_client):
    """Test handling of a non-existent secret."""
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.return_value = True
    mock_client_instance.secrets.kv.v2.read_secret_version.side_effect = hvac.exceptions.InvalidPath
    mock_hvac_client.return_value = mock_client_instance

    service = VaultService()
    with pytest.raises(hvac.exceptions.InvalidPath):
        service.read_secret('secret/data/nonexistent')
