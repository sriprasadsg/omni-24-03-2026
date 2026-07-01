# Contributing to Enterprise Omni-Agent Platform

## Prerequisites
- Python 3.13+, Node 24+, Docker 24+
- `git`, `pre-commit`

## Setup

```bash
git clone <repo>
cd enterprise-omni-agent-ai-platform

# Install pre-commit hooks (runs gitleaks + linters on every commit)
pip install pre-commit
pre-commit install

# Backend
cd backend && pip install -r requirements.txt

# Frontend
cd .. && npm install
```

## Running Locally

```bash
# Copy and fill in secrets
cp backend/.env.example backend/.env
# Generate secrets:
#   JWT_SECRET_KEY:     python -c "import secrets; print(secrets.token_urlsafe(64))"
#   MONGO_ROOT_PASSWORD: python -c "import secrets; print(secrets.token_urlsafe(32))"
#   REDIS_PASSWORD:     python -c "import secrets; print(secrets.token_urlsafe(32))"
#   EMAIL_ENCRYPTION_KEY: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up        # starts mongo, redis, backend, frontend-dev
```

Frontend: http://localhost:3000 | Backend API docs: http://localhost:5000/docs

## Branching

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready, protected |
| `develop` | Integration branch |
| `feature/<name>` | New features |
| `fix/<issue>` | Bug fixes |
| `chore/<name>` | Tooling, deps, refactors |

PRs target `develop`. `develop` → `main` is a release merge.

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(auth): add TOTP backup codes
fix(agent): handle offline message buffer flush race condition
chore(deps): bump cryptography to 42.0.1
test(ssrf): add DNS-bypass validation tests
```

Types: `feat`, `fix`, `chore`, `test`, `docs`, `refactor`, `perf`, `ci`

## Tests

```bash
# Backend (from backend/)
pytest tests/ --tb=short -q --cov=. --cov-report=term-missing

# Frontend
npm test
```

All PRs must pass CI. Coverage must not drop below the current gate.

## Security

- **Never commit secrets** — gitleaks pre-commit hook will block it
- Sensitive findings go to the security contact in `backend/static/.well-known/security.txt`
- See `docs/secrets.md` for secrets management guidance

## Code Style

- **Python**: ruff (enforced in CI), 4-space indent, 120-char line limit
- **TypeScript**: ESLint + Prettier, 2-space indent
- **No comments** unless explaining a non-obvious constraint or workaround
- Keep files under 500 lines; split if larger

## PR Checklist

- [ ] Tests added/updated for changed behaviour
- [ ] CI passes (lint, type-check, tests, security scan)
- [ ] No hardcoded secrets or credentials
- [ ] `backend/.env.example` updated if new env vars added
- [ ] CHANGELOG.md entry added
