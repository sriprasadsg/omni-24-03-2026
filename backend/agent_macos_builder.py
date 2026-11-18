"""The macOS agent download: the signed, notarised installer package (built on a Mac with
agent-install/macos/build-pkg.sh and published as backend/static/omni-agent-<version>-macos.pkg)
zipped with the tenant's config.yaml. The package's postinstall reads config.yaml from the folder
the package is opened from, so one signed package serves every tenant."""
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException
from fastapi.responses import Response

from agent_installer_builders import config_yaml_text

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
FOLDER = "OmniAgent-macOS"
_PKG_RE = re.compile(r"^omni-agent-(\d+)\.(\d+)\.(\d+)-macos\.pkg$")

_README = """Omni-Agent {version} for macOS

Keep OmniAgent.pkg and config.yaml together in this folder.

To install, open OmniAgent.pkg and follow the installer, or run:
  sudo installer -pkg OmniAgent.pkg -target /

The agent runs as a launchd daemon (com.omniagent.agent) from
/Library/Application Support/OmniAgent and enrolls with {api_url}.
To remove it: sudo "/Library/Application Support/OmniAgent/uninstall.sh"
"""


def latest_pkg(static_dir: Path = STATIC_DIR) -> Optional[Tuple[str, Path]]:
    """(version, path) of the newest published macOS package, or None."""
    best = None
    for path in static_dir.glob("omni-agent-*-macos.pkg"):
        match = _PKG_RE.match(path.name)
        if match:
            version = tuple(int(part) for part in match.groups())
            if best is None or version > best[0]:
                best = (version, path)
    return (".".join(map(str, best[0])), best[1]) if best else None


def build_macos_zip(tenant_name: str, registration_key: str, api_url: str,
                    static_dir: Path = STATIC_DIR) -> Response:
    found = latest_pkg(static_dir)
    if not found:
        raise HTTPException(status_code=503, detail=(
            "The macOS installer is not published on this server yet. Build it on a Mac with "
            "agent-install/macos/build-pkg.sh and copy the package to backend/static/."))
    version, pkg = found
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(pkg, f"{FOLDER}/OmniAgent.pkg", compress_type=zipfile.ZIP_STORED)  # already compressed
        archive.writestr(f"{FOLDER}/config.yaml", config_yaml_text(api_url, registration_key))
        archive.writestr(f"{FOLDER}/README.txt", _README.format(version=version, api_url=api_url))
    tenant_safe = re.sub(r"[^A-Za-z0-9._-]", "-", tenant_name).lower()
    logger.info("macOS agent %s zipped for tenant %s", version, tenant_safe)
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="OmniAgent-macOS-{tenant_safe}.zip"'})
