#!/usr/bin/env python3
"""OmniAgent CLI — frameworks, scan, findings, score commands."""
import os, sys, json, requests

API_URL = os.environ.get("OMNI_API_URL", "http://localhost:5000")
API_TOKEN = os.environ.get("OMNI_API_TOKEN", "")


def _headers():
    h = {"Content-Type": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


def _get(path: str, params: dict = None):
    r = requests.get(f"{API_URL}{path}", headers=_headers(), params=params)
    r.raise_for_status()
    return r.json()


def _post(path: str, data: dict = None):
    r = requests.post(f"{API_URL}{path}", headers=_headers(), json=data or {})
    r.raise_for_status()
    return r.json()


def cmd_frameworks_list(args):
    data = _get("/api/compliance/frameworks")
    for fw in data.get("frameworks", []):
        print(f"{fw.get('id', ''):20s} {fw.get('name', '')}")
    return 0


def cmd_scan_cloud(args):
    provider = args[0] if args else "digitalocean"
    account_id = args[1] if len(args) > 1 else ""
    result = _post("/api/mcp/execute/run_cloud_check", {"provider": provider, "account_id": account_id})
    print(json.dumps(result.get("result", result), indent=2))
    return 0


def cmd_findings_list(args):
    sev = args[0] if args else None
    params = {"severity": sev, "limit": 20} if sev else {"limit": 20}
    data = _get("/api/ocsf/findings", params)
    items = data.get("items", [])
    print(f"{'Title':50s} {'Severity':10s}")
    print("-" * 60)
    for f in items[:10]:
        title = f.get("finding", {}).get("title", "")[:48]
        sev = f.get("severity", "")
        print(f"{title:50s} {sev:10s}")
    return 0


def cmd_score(args):
    framework = args[0] if args else "soc2"
    result = _post("/api/mcp/execute/get_compliance_score", {"framework": framework})
    data = result.get("result", {})
    print(f"Framework: {data.get('framework', framework)}")
    print(f"Score:     {data.get('score', 0)}%")
    print(f"Passing:   {data.get('passing', 0)}/{data.get('total', 0)}")
    return 0


COMMANDS = {
    "frameworks list": cmd_frameworks_list,
    "scan cloud": cmd_scan_cloud,
    "findings list": cmd_findings_list,
    "score": cmd_score,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: omni-cli.py <command> [args...]")
        print("Commands: frameworks list, scan cloud [provider] [account-id], findings list [severity], score [framework]")
        return 1
    cmd = " ".join(sys.argv[1:])
    for prefix, fn in sorted(COMMANDS.items(), key=lambda x: -len(x[0])):
        if cmd.startswith(prefix):
            rest = cmd[len(prefix):].strip().split()
            return fn(rest)
    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
