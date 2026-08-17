import os

VAULT_ADDR = os.environ.get('VAULT_ADDR', 'http://127.0.0.1:8200')
VAULT_TOKEN = os.environ.get('VAULT_TOKEN')
