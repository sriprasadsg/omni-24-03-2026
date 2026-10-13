"""Devices slice (76-01 seed, filled by 76-06)."""
from catalogue_guards import catalogue_guard

MOUNTS = {
    ("mdm_endpoints", "router"): catalogue_guard(
        "mobileDeviceManagement",
        read=("view:mdm",),
        write=("manage:assets",),
    ),
}
