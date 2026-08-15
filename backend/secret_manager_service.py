import hvac
from backend.config import VAULT_ADDR, VAULT_TOKEN

class SecretManagerService:
    def __init__(self):
        self.url = VAULT_ADDR
        self.token = VAULT_TOKEN
        self.client = hvac.Client(url=self.url, token=self.token)

    def connect(self):
        """
        Establishes connection to HashiCorp Vault.
        This effectively performs a client initialization check for connectivity.
        """
        if not self.client.is_authenticated():
            if self.token:
                self.client.token = self.token
                if not self.client.is_authenticated():
                    raise hvac.exceptions.VaultError("Failed to authenticate with Vault using provided token.")
            else:
                raise hvac.exceptions.VaultError("Vault token not provided and client not authenticated.")
        return True

    def read_secret(self, path: str):
        """
        Reads a secret from HashiCorp Vault. Assumes KV v2 engine.
        path format: secret/data/my-secret
        """
        # Ensure client is authenticated before reading
        if not self.client.is_authenticated():
            self.connect() # Attempt to connect/authenticate

        mount_point_and_path = path.split('/', 1)
        if len(mount_point_and_path) < 2:
            raise ValueError(f"Invalid Vault path format: {path}. Expected 'mount_point/path'.")

        mount_point = mount_point_and_path[0]
        secret_path = mount_point_and_path[1]

        # remove 'data/' prefix if present for hvac v2 read_secret_version
        if secret_path.startswith('data/'):
            secret_path = secret_path[len('data/'):]

        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                mount_point=mount_point,
                path=secret_path
            )
            return response['data']['data']
        except hvac.exceptions.VaultError as e:
            raise hvac.exceptions.VaultError(f"Error reading secret from Vault at path '{path}': {e}")

    def write_secret(self, path: str, data: dict):
        """
        Writes a secret to HashiCorp Vault. Assumes KV v2 engine.
        path format: secret/data/my-secret
        """
        # Ensure client is authenticated before writing
        if not self.client.is_authenticated():
            self.connect() # Attempt to connect/authenticate

        mount_point_and_path = path.split('/', 1)
        if len(mount_point_and_path) < 2:
            raise ValueError(f"Invalid Vault path format: {path}. Expected 'mount_point/path'.")

        mount_point = mount_point_and_path[0]
        secret_path = mount_point_and_path[1]

        if secret_path.startswith('data/'):
            secret_path = secret_path[len('data/'):]

        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                mount_point=mount_point,
                path=secret_path,
                secret=data
            )
        except hvac.exceptions.VaultError as e:
            raise hvac.exceptions.VaultError(f"Error writing secret to Vault at path '{path}': {e}")