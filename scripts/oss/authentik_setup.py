"""Set up the local authentik for the platform's checks (run as root by `scripts/oss/oss.sh wire authentik`).

Creates, each only once:
  * the group "Omni-Agent users" with two test users (oss.test.anna, oss.test.ben) to provision;
  * the service account "omni-agent-log-reader" with a role that may only view events, and an API token for it,
    written to /opt/omni-oss/authentik/omni-log-token for the platform's authentik log source;
  * the SCIM provider "Omni-Agent SCIM" (authentik's default SCIM mappings, certificate verified) and the
    application "Omni-Agent" carrying it, bound to that group so only its members are provisioned. Its token is
    the platform's SCIM token, read from /opt/omni-oss/authentik/omni-scim-token;
    until that file exists the provider is left in dry-run so it sends nothing.

The bootstrap admin token comes from /opt/omni-oss/authentik/.env. Nothing secret is printed.
"""
import json
import os
import sys
import urllib.error
import urllib.request

DIR = "/opt/omni-oss/authentik"
API = "http://127.0.0.1:9000/api/v3"
GROUP = "Omni-Agent users"
USERS = [("oss.test.anna", "Anna Test", "anna.test@oss-test.example"), ("oss.test.ben", "Ben Test", "ben.test@oss-test.example")]
READER, ROLE, TOKEN_ID = "omni-agent-log-reader", "Omni-Agent log reader", "omni-agent-log-source"
PROVIDER, APP_SLUG = "Omni-Agent SCIM", "omni-agent"
PLACEHOLDER = "not-set-yet-see-omni-scim-token"


def bootstrap_token() -> str:
    for line in open(os.path.join(DIR, ".env")):
        if line.startswith("AUTHENTIK_BOOTSTRAP_TOKEN="):
            return line.split("=", 1)[1].strip()
    sys.exit("no AUTHENTIK_BOOTSTRAP_TOKEN in the authentik .env")


def call(method: str, path: str, body=None):
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"authentik refused {method} {path}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
    return json.loads(raw) if raw else {}


def find(path: str, **query):
    q = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in query.items())
    return (call("GET", f"{path}?{q}").get("results") or [None])[0]


def write_secret(name: str, value: str) -> None:
    path = os.path.join(DIR, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)


def main(scim_url: str) -> None:
    group = find("/core/groups/", name=GROUP) or call("POST", "/core/groups/", {"name": GROUP})
    for username, name, email in USERS:
        if not find("/core/users/", username=username):
            call("POST", "/core/users/", {"username": username, "name": name, "email": email, "is_active": True,
                                         "groups": [group["pk"]], "path": "omni-test"})
    reader = find("/core/users/", username=READER)
    if not reader:
        call("POST", "/core/users/service_account/", {"name": READER, "create_group": False, "expiring": False})
        reader = find("/core/users/", username=READER)
    role = find("/rbac/roles/", name=ROLE)
    if not role:
        role = call("POST", "/rbac/roles/", {"name": ROLE})
        call("POST", f"/rbac/permissions/assigned_by_roles/{role['pk']}/assign/", {"permissions": ["authentik_events.view_event"]})
        call("POST", f"/rbac/roles/{role['pk']}/add_user/", {"pk": reader["pk"]})
    if not find("/core/tokens/", identifier=TOKEN_ID):
        call("POST", "/core/tokens/", {"identifier": TOKEN_ID, "intent": "api", "user": reader["pk"], "expiring": False,
                                       "description": "Omni-Agent authentik log source (view events only)"})
    if not os.path.exists(os.path.join(DIR, "omni-log-token")):
        write_secret("omni-log-token", call("GET", f"/core/tokens/{TOKEN_ID}/view_key/")["key"])
    scim_file = os.path.join(DIR, "omni-scim-token")
    scim_token = open(scim_file).read().strip() if os.path.exists(scim_file) else ""
    mapping = {m["managed"]: m["pk"] for m in call("GET", "/propertymappings/provider/scim/")["results"] if m.get("managed")}
    spec = {"name": PROVIDER, "url": scim_url, "token": scim_token or PLACEHOLDER, "verify_certificates": True,
            "exclude_users_service_account": True, "group_filters": [group["pk"]], "dry_run": not scim_token,
            "property_mappings": [mapping["goauthentik.io/providers/scim/user"]],
            "property_mappings_group": [mapping["goauthentik.io/providers/scim/group"]]}
    provider = find("/providers/scim/", name=PROVIDER)
    provider = call("PATCH", f"/providers/scim/{provider['pk']}/", spec) if provider else call("POST", "/providers/scim/", spec)
    app = find("/core/applications/", slug=APP_SLUG, superuser_full_list="true") or call(
        "POST", "/core/applications/", {"name": "Omni-Agent", "slug": APP_SLUG, "backchannel_providers": [provider["pk"]]})
    # SCIM syncs the users who may use the application (group_filters scopes groups only): bind the group to it
    if not find("/policies/bindings/", target=app["pk"], group=group["pk"]):
        call("POST", "/policies/bindings/", {"target": app["pk"], "group": group["pk"], "order": 0, "enabled": True})
    print(f"group '{GROUP}' with {len(USERS)} test users; log-reader token in {DIR}/omni-log-token")
    print(f"SCIM provider '{PROVIDER}' -> {scim_url}: " + ("live (token set)" if scim_token else
          f"dry run until the platform's SCIM token is in {scim_file} (scripts/oss/oss.sh scim-token)"))


if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("run as root (scripts/oss/oss.sh wire authentik)")
    TOKEN = bootstrap_token()
    main(sys.argv[1] if len(sys.argv) > 1 else "https://10.0.0.4/api/scim/v2")
