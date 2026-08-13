import os
import hvac

class VaultService:
    def __init__(self):
        self.url = os.environ.get('VAULT_ADDR', 'http://127.0.0.1:8200')
        self.token = os.environ.get('VAULT_TOKEN')
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
