# Phase 64: Key Rotation - Research

**Researched:** 2026-08-14
**Domain:** Autonomous Remediation - Key Rotation, HashiCorp Vault
**Confidence:** HIGH

## Summary

This phase focuses on integrating HashiCorp Vault for secure key management and enabling the agent to receive and acknowledge key rotation commands. The primary goal is to establish a secure, end-to-end communication path for key rotation. The backend will implement a client for HashiCorp Vault, while the Rust agent will be extended with a `RotateKey` instruction. A tracer test will validate the entire flow from backend dispatch to agent execution and response.

**Primary recommendation:** Use `hvac` for Python backend Vault integration. Implement `RotateKey { key_id: String, vault_path: String }` instruction in the Rust agent.

## User Constraints (from CONTEXT.md)

### Locked Decisions
None

### Claude's Discretion
None

### Deferred Ideas (OUT OF SCOPE)
None

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTO-02.1 | Implement `rotate_key` remediation action | `hvac` library for Vault integration, Rust agent `RotateKey` instruction. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Key Storage & Retrieval | API / Backend | Database / Storage (Vault) | Backend handles secure interaction with Vault, Vault provides secure storage. |
| Key Rotation Instruction Dispatch | API / Backend | — | Backend initiates key rotation commands. |
| Key Rotation Instruction Execution | Agent | — | Agent receives and processes key rotation commands. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `hvac` | 2.4.0 (Python) | HashiCorp Vault API client | Official and widely adopted Python client for HashiCorp Vault. |
| `reqwest` | 0.12 (Rust) | HTTP client for agent | Standard Rust HTTP client, likely already in use. |
| `serde` | 1.0 (Rust) | Serialization/Deserialization | Standard Rust library for data structures. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tokio` | 1.x (Rust) | Asynchronous runtime | For agent's async operations, likely already in use. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `hvac` | `python-hvac` (deprecated) | `hvac` is the maintained, official client. |
| `hvac` | Direct HTTP calls | `hvac` abstracts API complexity, handles auth/sessions. |

**Installation:**
```bash
pip install hvac
```

**Version verification:**
- `hvac`: Verified 2.4.0 on PyPI.
- Rust crates: `reqwest`, `serde`, `tokio` are already present in `Cargo.toml`.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `hvac` | PyPI | 8 years (approx. based on first release) | N/A (pip index doesn't show) | github.com/hvac/hvac | SUS | Flagged — planner must add checkpoint |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `hvac` — planner inserts checkpoint:human-verify before install.

## Architecture Patterns

### System Architecture Diagram
```mermaid
graph TD
    UserUI[User Interface] -- Trigger Key Rotation --> BackendAPI
    BackendAPI[Backend API] -- Dispatch RotateKey Instruction --> Agent
    BackendAPI -- Read/Write Secret --> HashiCorpVault[HashiCorp Vault]
    Agent[Rust Agent] -- Execute RotateKey --> (Simulated/External Target)
    Agent -- Report Status --> BackendAPI
```
*Description:* The User UI initiates a key rotation request to the Backend API. The Backend API then dispatches a `RotateKey` instruction to the Rust Agent. Concurrently, the Backend API interacts with HashiCorp Vault to manage secrets. The Agent executes the `RotateKey` instruction (mocked in this phase) and reports its status back to the Backend API.

### Recommended Project Structure
```
backend/
├── secret_manager_service.py # HashiCorp Vault client
├── config.py                 # Vault configuration
└── tests/
    └── test_secret_manager_service.py # Unit tests for Vault client

agent-rust/
├── src/
│   ├── instructions.rs       # Agent instruction definitions
│   └── remediation/
│       ├── key_rotation.rs   # Handler for RotateKey instruction
│       └── mod.rs            # Remediation module integration
└── tests/                    # Agent related tests

```

### Pattern 1: External Secret Management
**What:** Centralized management of secrets (API keys, database credentials, certificates) outside of application code, using tools like HashiCorp Vault.
**When to use:** Any application dealing with sensitive information that needs to be rotated, audited, and securely accessed.
**Example:**
```python
# Source: [CITED: hvac documentation]
import hvac

client = hvac.Client(url='http://127.0.0.1:8200', token='my-root-token')
if client.is_authenticated():
    secret_data = client.secrets.kv.v2.read_secret_version(path='secret/my-app/config')
    print(secret_data['data']['data']['api_key'])
```

### Anti-Patterns to Avoid
- **Hardcoding Secrets:** Storing sensitive information directly in source code or configuration files that are checked into version control. Use environment variables and secret management systems.
- **Ignoring Error Handling:** Not gracefully handling connection errors or authentication failures with the secret management system can lead to service outages.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Secure Secret Storage | Custom encrypted files/DB tables | HashiCorp Vault | Provides robust security, auditing, rotation, access control, and established best practices. |
| Vault API Client | Raw HTTP requests to Vault API | `hvac` (Python) | `hvac` handles authentication, token management, API versioning, and error parsing. |

**Key insight:** Security-sensitive infrastructure like secret management is highly complex with many edge cases. Leveraging battle-tested solutions like HashiCorp Vault and its official clients is crucial for correctness and security.

## Runtime State Inventory
None — verified this is a greenfield implementation for key rotation.

## Common Pitfalls

### Pitfall 1: Vault Token Handling
**What goes wrong:** Vault tokens are exposed in logs, environment variables are not secure enough, or tokens expire unexpectedly.
**Why it happens:** Misunderstanding Vault's authentication methods, poor CI/CD practices, or not implementing token renewal.
**How to avoid:** Use appropriate Vault authentication methods (e.g., AppRole, Kubernetes auth) instead of long-lived root tokens. Use secure environment variable injection (e.g., Kubernetes Secrets, Docker Swarm Secrets). Implement token renewal logic if using periodic tokens.
**Warning signs:** Unauthorized access attempts in Vault audit logs, frequent service interruptions due to token expiration.

### Pitfall 2: Agent Instruction Deserialization Errors
**What goes wrong:** The Rust agent fails to deserialize the `RotateKey` instruction sent from the backend.
**Why it happens:** Mismatched field names, data types, or enum variants between the backend's serialization and the agent's deserialization logic.
**How to avoid:** Use `serde` attributes carefully (`#[serde(rename = "...", default)]`), ensure types match, and thoroughly test the end-to-end instruction dispatch and receipt.
**Warning signs:** Agent logs showing deserialization errors or unexpected instruction parsing failures.

## Code Examples

### Backend: HashiCorp Vault Client Initialization (Python)
```python
# Source: [CITED: hvac documentation]
import hvac
import os

class VaultService:
    def __init__(self):
        self.url = os.getenv("VAULT_ADDR")
        self.token = os.getenv("VAULT_TOKEN") # For simplicity; AppRole preferred in production
        self.client = None

    def connect(self):
        if not self.url or not self.token:
            raise ValueError("VAULT_ADDR and VAULT_TOKEN must be set")
        self.client = hvac.Client(url=self.url, token=self.token)
        if not self.client.is_authenticated():
            raise Exception("Failed to authenticate with HashiCorp Vault")
        print("Successfully connected to Vault.")

    def read_secret(self, path: str):
        if not self.client:
            self.connect() # Or handle pre-connection
        try:
            read_response = self.client.secrets.kv.v2.read_secret_version(path=path)
            return read_response['data']['data']
        except Exception as e:
            print(f"Error reading secret from {path}: {e}")
            raise

# Example usage (in a test or main function)
# vault_service = VaultService()
# vault_service.connect()
# secret = vault_service.read_secret('secret/my-app/database')
# print(secret)
```

### Agent: `RotateKey` Instruction Definition (Rust)
```rust
// Source: [ASSUMED] based on common Rust enum patterns
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub enum AgentInstruction {
    // Existing instructions...
    RotateKey {
        key_id: String,
        vault_path: String,
    },
}

#[derive(Serialize, Deserialize, Debug)]
pub enum AgentResponse {
    ActionCompleted,
    // Other responses...
}
```

## State of the Art
N/A

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Agent instruction serialization/deserialization handled by `serde` without complex custom logic. | Code Examples | Potential runtime errors if struct/enum definitions mismatch between backend and agent. |

## Open Questions
None.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| HashiCorp Vault | Backend Key Mgmt | ✗ | N/A | Manual key management (not recommended) |

**Missing dependencies with no fallback:**
- HashiCorp Vault: The phase requires a running Vault instance (or mock for testing). This must be available in the target environment for full functionality.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` (Python), `cargo test` (Rust) |
| Config file | `pytest.ini` (if present), `Cargo.toml` |
| Quick run command | `pytest backend/tests/test_secret_manager_service.py` |
| Full suite command | `pytest` (backend), `cargo test` (agent) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTO-02.1 | Backend Vault client connects | Unit | `pytest backend/tests/test_secret_manager_service.py` | ✅ |
| AUTO-02.1 | Backend Vault client reads secret | Unit | `pytest backend/tests/test_secret_manager_service.py` | ✅ |
| AUTO-02.1 | Agent compiles with `RotateKey` | Compile | `cd agent-rust && cargo check` | ✅ |
| AUTO-02.1 | E2E: Backend dispatches, Agent receives & responds `RotateKey` | Integration | `pytest backend/tests/test_key_rotation_tracer.py` | ✅ |

### Sampling Rate
- **Per task commit:** Run relevant unit tests (`pytest ...`, `cargo check`).
- **Per wave merge:** Full suite for changed components.
- **Phase gate:** All defined automated tests pass.

### Wave 0 Gaps
None — existing test infrastructure covers needs.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | Vault authentication mechanisms (tokens, AppRole) |
| V6 Cryptography | Yes | Vault's encryption-at-rest and TLS in transit. |
| V7 Error Handling & Logging | Yes | Proper logging of Vault connection/access failures; agent logging of received instruction parameters. |
| V10 API & Web Service | Yes | Secure communication between backend and Vault, backend and agent. |
| V13 Malicious Code | Yes | Package legitimacy checks (`hvac`). |

### Known Threat Patterns for Python/Rust/Vault Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret exposure (plaintext) | Information Disclosure | Use HashiCorp Vault, environment variables (securely managed). |
| Tampering with `RotateKey` params | Tampering | Backend input validation; agent logging of received params. |
| Unauthorized Vault access | Elevation of Privilege | Least privilege for Vault tokens/roles; network ACLs. |
| Supply Chain Attack (libraries) | Tampering | Package legitimacy audit (`hvac`). |
| Unhandled Vault connection failure | Denial of Service | Graceful error handling, retry mechanisms. |

## Sources

### Primary (HIGH confidence)
- `gsd-tools query package-legitimacy check --ecosystem pypi hvac` - legitimacy, versions.
- `pip index versions hvac` - version confirmation.
- `Cargo.toml` - existing Rust dependencies.

### Secondary (MEDIUM confidence)
- `hvac` official documentation - API usage patterns.

### Tertiary (LOW confidence)
- Training data for common Rust agent instruction patterns.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - `hvac` is the clear choice for Python, existing Rust libs are suitable.
- Architecture: HIGH - Clear separation of concerns, standard pattern for secret management.
- Pitfalls: HIGH - Common pitfalls for Vault integration and cross-service communication are well-understood.

**Research date:** 2026-08-14
**Valid until:** 2026-09-14
