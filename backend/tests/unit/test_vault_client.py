import pytest
from unittest.mock import patch, MagicMock
from backend.vault_client import VaultClient
import hvac

@patch('hvac.Client')
def test_vault_client_connect_success(mock_hvac_client):
    """Test that the Vault client initializes and connects successfully."""
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.return_value = True
    mock_hvac_client.return_value = mock_client_instance

    service = VaultClient()
    assert service.client is not None
    assert service.client.is_authenticated()

@patch('hvac.Client')
def test_vault_client_connect_failure(mock_hvac_client):
    """Test that the Vault client handles connection errors gracefully."""
    mock_hvac_client.side_effect = hvac.exceptions.VaultDown

    with pytest.raises(hvac.exceptions.VaultDown):
        VaultClient()

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

    service = VaultClient()
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

    service = VaultClient()
    with pytest.raises(hvac.exceptions.InvalidPath):
        service.read_secret('secret/data/nonexistent')

@patch('hvac.Client')
def test_write_secret_success(mock_hvac_client):
    """Test successfully writing a secret to Vault."""
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.return_value = True
    mock_hvac_client.return_value = mock_client_instance

    service = VaultClient()
    service.write_secret('secret/data/new-secret', {'new_key': 'new_value'})
    service.client.secrets.kv.v2.create_or_update_secret.assert_called_with(
        mount_point='secret', path='new-secret', secret={'new_key': 'new_value'}
    )
