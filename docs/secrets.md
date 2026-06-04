# Secrets Management

## Required Secrets

| Variable | Purpose | Generate With |
|----------|---------|---------------|
| `JWT_SECRET_KEY` | Signs all access/refresh tokens | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `SUPER_ADMIN_PASSWORD` | Initial super admin account | Choose a strong password (16+ chars) |
| `MONGO_ROOT_PASSWORD` | MongoDB admin auth | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `REDIS_PASSWORD` | Redis auth | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `EMAIL_ENCRYPTION_KEY` | Encrypts stored SMTP passwords | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

## Development (Local)

Store secrets in `backend/.env` (git-ignored):

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with generated values
```

The application will refuse to start in production (`APP_ENV=production`) if any of the above contain placeholder values like `changeme_*`.

## Production Options

### Option 1: Environment Variables (simplest)
Set the variables directly in your deployment environment. For Docker Compose:

```bash
export MONGO_ROOT_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export REDIS_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
docker compose --profile production up -d
```

### Option 2: Docker Secrets
```yaml
# docker-compose.yml
services:
  backend:
    secrets:
      - jwt_secret
      - mongo_password
secrets:
  jwt_secret:
    external: true
  mongo_password:
    external: true
```

```bash
echo "$(python -c "import secrets; print(secrets.token_urlsafe(64))")" | docker secret create jwt_secret -
```

Then update `backend/app.py` to read from `/run/secrets/<name>` when the env var is not set.

### Option 3: HashiCorp Vault
```bash
vault kv put secret/omniagent \
  jwt_secret_key="$(python -c "import secrets; print(secrets.token_urlsafe(64))")" \
  mongo_root_password="$(python -c "import secrets; print(secrets.token_urlsafe(32))")"
```

Use the Vault Agent sidecar or `hvac` Python SDK to inject secrets at runtime.

### Option 4: AWS Secrets Manager
```python
import boto3, json
client = boto3.client("secretsmanager", region_name="us-east-1")
secret = json.loads(client.get_secret_value(SecretId="omniagent/prod")["SecretString"])
os.environ["JWT_SECRET_KEY"] = secret["jwt_secret_key"]
```

### Option 5: Kubernetes Secrets
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: omniagent-secrets
  namespace: omniagent
type: Opaque
stringData:
  JWT_SECRET_KEY: "<generated>"
  MONGO_ROOT_PASSWORD: "<generated>"
  REDIS_PASSWORD: "<generated>"
  SUPER_ADMIN_PASSWORD: "<your-password>"
```

```bash
kubectl create secret generic omniagent-secrets \
  --from-literal=JWT_SECRET_KEY="$(python -c "import secrets; print(secrets.token_urlsafe(64))")" \
  --namespace omniagent
```

## Rotation

### JWT Secret Key
Rotating `JWT_SECRET_KEY` immediately invalidates all active sessions. To rotate with zero downtime:
1. Add `JWT_SECRET_KEY_PREV` env var (old key)
2. Update `authentication_service.py` to try both keys during verification
3. Deploy new secret
4. Remove `JWT_SECRET_KEY_PREV` after all tokens from the old key expire (60–120 min)

### MongoDB/Redis Passwords
Update in the deployment environment, then restart services. Connections will re-authenticate on reconnect.

### Email Encryption Key
Rotating `EMAIL_ENCRYPTION_KEY` breaks decryption of any SMTP passwords stored in the database. Before rotation:
1. Use the old key to decrypt and re-encrypt all SMTP passwords with the new key
2. Or delete all stored SMTP configs and have users re-enter them

## Security Checklist

- [ ] No secrets in `git log --all` (run `git filter-repo` if needed — see main README)
- [ ] `backend/.env` is in `.gitignore`
- [ ] `JWT_SECRET_KEY` is at least 64 random bytes
- [ ] `MONGO_ROOT_PASSWORD` is at least 16 random chars
- [ ] Production deploys with `APP_ENV=production` to enable placeholder checks
- [ ] Secrets rotated if any were ever committed to git
- [ ] gitleaks pre-commit hook installed: `pre-commit install`
