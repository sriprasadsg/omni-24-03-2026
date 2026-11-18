"""The macOS download ships the newest published signed package with the tenant's config.yaml.

Value: protects=a Mac enrolling into the right tenant from a package nobody re-signs per tenant (the
postinstall reads config.yaml beside the package); fails_when=the zip lacks the package or the config, an
older package wins over a newer one, or a missing package returns something other than a clear 503;
no_claim=whether the package itself installs (that needs a Mac)."""
import io
import os
import sys
import zipfile

import pytest
import yaml
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_macos_builder as m  # noqa: E402


def _publish(static_dir, version, body=b"xar!"):
    path = static_dir / f"omni-agent-{version}-macos.pkg"
    path.write_bytes(body + version.encode())
    return path


def test_without_a_published_package_the_download_says_how_to_publish_one(tmp_path):
    (tmp_path / "omni-agent-2.1.21-windows.exe").write_bytes(b"MZ")
    with pytest.raises(HTTPException) as err:
        m.build_macos_zip("Acme", "reg_x", "https://10.0.0.5", static_dir=tmp_path)
    assert err.value.status_code == 503
    assert "build-pkg.sh" in err.value.detail


def test_the_newest_version_wins_by_number_not_by_name(tmp_path):
    _publish(tmp_path, "2.1.9")
    newest = _publish(tmp_path, "2.1.10")
    (tmp_path / "omni-agent-latest-macos.pkg").write_bytes(b"not a release")
    assert m.latest_pkg(tmp_path) == ("2.1.10", newest)


def test_the_zip_holds_the_package_the_tenant_config_and_a_readme(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_CA_CERT_FILE", raising=False)
    pkg = _publish(tmp_path, "2.1.22")
    resp = m.build_macos_zip("Acme Corp", "reg_acme", "https://10.0.0.5", static_dir=tmp_path)
    assert resp.media_type == "application/zip"
    assert 'filename="OmniAgent-macOS-acme-corp.zip"' in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.body)) as archive:
        assert sorted(archive.namelist()) == ["OmniAgent-macOS/OmniAgent.pkg", "OmniAgent-macOS/README.txt",
                                              "OmniAgent-macOS/config.yaml"]
        assert archive.read("OmniAgent-macOS/OmniAgent.pkg") == pkg.read_bytes()
        cfg = yaml.safe_load(archive.read("OmniAgent-macOS/config.yaml"))
        assert (cfg["registration_key"], cfg["api_base_url"]) == ("reg_acme", "https://10.0.0.5")
        assert "2.1.22" in archive.read("OmniAgent-macOS/README.txt").decode()
