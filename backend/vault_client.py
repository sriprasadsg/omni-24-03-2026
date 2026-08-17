import hvac
from backend.config import VAULT_ADDR, VAULT_TOKEN

class VaultClient:
    def __init__(self):
        self.url = VAULT_ADDR
        self.token = VAULT_TOKEN
        self.client = hvac.Client(url=self.url, token=self.token)

    def read_secret(self, path: str):
        # Assuming KV v2 engine for now
        # path format: secret/data/my-secret
        mount_point, path = path.split('/', 1)
        # remove 'data/' prefix if present for hvac v2 read_secret_version
        if path.startswith('data/'):
            path = path[len('data/'):]

        response = self.client.secrets.kv.v2.read_secret_version(
            mount_point=mount_point,
            path=path
        )
        return response['data']['data']

    def write_secret(self, path: str, data: dict):
        mount_point, path = path.split('/', 1)
        if path.startswith('data/'):
            path = path[len('data/'):]

        self.client.secrets.kv.v2.create_or_update_secret(
            mount_point=mount_point,
            path=path,
            secret=data
        )
