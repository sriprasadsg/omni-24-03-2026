"""The frontend names every built-in role the way the backend's role catalogue does (QA 2026-11-04).

Value: protects=no screen shows a stored key such as "partner_admin" for a built-in role;
fails_when=a built-in role is added or renamed in rbac_defaults.BUILTIN_ROLES without its label in
utils/permissions.ts BUILTIN_ROLE_LABELS, or a label disagrees with the backend's readable name.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rbac_defaults

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _frontend_labels():
    with open(os.path.join(REPO, "utils", "permissions.ts"), encoding="utf-8") as handle:
        text = handle.read()
    block = re.search(r"const BUILTIN_ROLE_LABELS: Record<string, string> = \{(.*?)\};", text, re.S)
    assert block, "BUILTIN_ROLE_LABELS not found in utils/permissions.ts"
    return dict(re.findall(r"(\w+): '([^']+)'", block.group(1)))


def _readable(role):
    """The backend's readable name: the stored name when it already reads as words, else display_name."""
    return role.name if (role.name != role.name.lower() or " " in role.name) else role.display_name


def test_every_built_in_role_has_the_backend_label():
    expected = {role.key: _readable(role) for role in rbac_defaults.BUILTIN_ROLES if role.key != "super_admin"}
    assert _frontend_labels() == expected
