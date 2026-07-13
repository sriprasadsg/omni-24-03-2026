#!/usr/bin/env python3
"""OmniAgent CLI — frameworks, scan, findings, score commands."""
import json
import os
import sys

import click
import requests

API_URL = os.environ.get("OMNI_API_URL", "http://localhost:5000")
API_TOKEN = os.environ.get("OMNI_API_TOKEN", "")
_TIMEOUT_SECONDS = 30


def _headers():
    h = {"Content-Type": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


def _get(path: str, params: dict = None):
    try:
        r = requests.get(f"{API_URL}{path}", headers=_headers(), params=params, timeout=_TIMEOUT_SECONDS)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _post(path: str, data: dict = None):
    try:
        r = requests.post(f"{API_URL}{path}", headers=_headers(), json=data or {}, timeout=_TIMEOUT_SECONDS)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.group()
def cli():
    """OmniAgent CLI — frameworks, scan, findings, score commands."""


@cli.group()
def frameworks():
    """Compliance framework commands."""


@frameworks.command("list")
def frameworks_list():
    """List compliance frameworks."""
    data = _get("/api/compliance/frameworks")
    for fw in data.get("frameworks", []):
        click.echo(f"{fw.get('id', ''):20s} {fw.get('name', '')}")


@cli.group()
def scan():
    """Cloud security scan commands."""


@scan.command("cloud")
@click.option("--provider", default="digitalocean", help="Cloud provider (aws/azure/gcp)")
@click.option("--account-id", default="", help="Cloud account ID")
def scan_cloud(provider, account_id):
    """Run a cloud security check against a provider account."""
    result = _post("/api/mcp/execute/run_cloud_check", {"provider": provider, "account_id": account_id})
    click.echo(json.dumps(result.get("result", result), indent=2))


@cli.group()
def findings():
    """Security findings commands."""


@findings.command("list")
@click.option("--severity", default=None, help="Filter by severity (critical/high/medium/low)")
@click.option("--limit", default=20, type=int, help="Max results to fetch")
def findings_list(severity, limit):
    """List security findings."""
    params = {"limit": limit}
    if severity:
        params["severity"] = severity
    data = _get("/api/ocsf/findings", params)
    items = data.get("items", [])
    click.echo(f"{'Title':50s} {'Severity':10s}")
    click.echo("-" * 60)
    for f in items[:10]:
        title = f.get("finding", {}).get("title", "")[:48]
        sev = f.get("severity", "")
        click.echo(f"{title:50s} {sev:10s}")


@cli.command()
@click.option("--framework", default="soc2", help="Framework id (soc2/iso27001/pci_dss/etc)")
def score(framework):
    """Get overall compliance score for a framework."""
    result = _post("/api/mcp/execute/get_compliance_score", {"framework": framework})
    data = result.get("result", {})
    click.echo(f"Framework: {data.get('framework', framework)}")
    click.echo(f"Score:     {data.get('score', 0)}%")
    click.echo(f"Passing:   {data.get('passing', 0)}/{data.get('total', 0)}")


if __name__ == "__main__":
    cli()
