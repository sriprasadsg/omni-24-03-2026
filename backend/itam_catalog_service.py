"""
ITAM catalog service — the fieldset contract shared between the catalog router (asset Model
create/update) and the asset write path (56-04 attaches customFields values to individual
assets).

Boundary note: fieldsets are stored embedded on the asset Model document, not in a separate
`custom_field_definitions` collection. Grouping fields into named fieldsets attached at the
model level is the deliberate MVP boundary ITAM-CAT-04 asks for; a global reusable
field-definition registry is scope a later phase adding cross-model reporting or filtering
over custom fields would introduce, not this one.

This module performs no database I/O — every function here takes plain dicts/lists and
returns plain values so both the router and 56-04's asset write path can call it directly.
"""
import re
from typing import Any, Dict, List

_FIELD_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SUPPORTED_TYPES = {"text", "number", "date", "boolean", "select"}


def validate_fieldsets(fieldsets: List[dict]) -> None:
    """Validate the fieldset definitions attached to an asset Model.

    Raises ValueError with a specific message when:
      - a field key repeats anywhere across all fieldsets on the model,
      - a key is not identifier-shaped (leading letter, then letters/digits/underscores),
      - a type is outside the supported set, or
      - a select-typed field carries no non-empty options list.
    """
    seen_keys = set()
    for fieldset in fieldsets:
        for field in fieldset.get("fields", []):
            key = field.get("key", "")
            if not _FIELD_KEY_RE.match(key):
                raise ValueError(
                    f"Field key '{key}' is not identifier-shaped (must start with a letter, "
                    "followed by letters, digits, or underscores)."
                )
            if key in seen_keys:
                raise ValueError(f"Field key '{key}' is duplicated across fieldsets on this model.")
            seen_keys.add(key)

            field_type = field.get("type")
            if field_type not in _SUPPORTED_TYPES:
                raise ValueError(f"Field '{key}' has unsupported type '{field_type}'.")
            if field_type == "select":
                options = field.get("options") or []
                if not options:
                    raise ValueError(f"Select field '{key}' must declare a non-empty options list.")


def flatten_fieldsets(model_doc: dict) -> List[dict]:
    """Flatten a model document's fieldsets into an ordered list of field entries.

    Each entry is `{"fieldsetName", "key", "label", "type", "required", "options"}`,
    walked in declaration order (fieldset order, then within-fieldset field order). A
    field with no `label` falls back to its `key`. This is a read-side convenience over
    the same `fieldsets` shape `validate_fieldsets` already enforces — it performs no
    validation of its own.
    """
    flattened: List[dict] = []
    for fieldset in model_doc.get("fieldsets") or []:
        fieldset_name = fieldset.get("name")
        for field in fieldset.get("fields") or []:
            key = field.get("key")
            flattened.append({
                "fieldsetName": fieldset_name,
                "key": key,
                "label": field.get("label") or key,
                "type": field.get("type"),
                "required": bool(field.get("required")),
                "options": field.get("options") or [],
            })
    return flattened


def collect_field_defs(model_doc: dict) -> Dict[str, dict]:
    """Flatten every fieldset on a model document into a key -> definition mapping."""
    defs: Dict[str, dict] = {}
    for fieldset in model_doc.get("fieldsets", []) or []:
        for field in fieldset.get("fields", []) or []:
            defs[field["key"]] = field
    return defs


def count_field_usage_keys(model_doc: dict) -> List[str]:
    """Return the distinct field keys declared on a model.

    Single source of "what to count" for the fields route's per-key asset usage count, so
    that counting logic lives once in the router and this module stays DB-I/O-free.
    """
    return list(collect_field_defs(model_doc).keys())


def validate_custom_field_values(field_defs: Dict[str, dict], values: Dict[str, Any]) -> List[str]:
    """Check a customFields value mapping against a model's flattened field definitions.

    Returns a list of human-readable problems: an unknown value key not present in
    `field_defs`, a required definition with no supplied value, and a select value outside
    its declared options list. An empty returned list means the mapping is valid. This is the
    single point 56-04's asset write path calls.
    """
    problems: List[str] = []
    for key in values:
        if key not in field_defs:
            problems.append(f"Unknown custom field '{key}'.")

    for key, definition in field_defs.items():
        if definition.get("required") and key not in values:
            problems.append(f"Missing required custom field '{key}'.")
        elif key in values and definition.get("type") == "select":
            options = definition.get("options") or []
            if values[key] not in options:
                problems.append(f"Value for '{key}' is not one of the allowed options.")

    return problems
