"""Pluggable source adapters.

To add a new source: drop a file in `app/adapters/sources/` that defines a
`SourceAdapter` subclass with `metadata: AdapterMetadata` and `@register_adapter`.
That's it — orchestrator, UI, and reporting layers pick it up automatically.

External packages can also register adapters via the `sourcing.adapters`
entry-point group in their `pyproject.toml`.
"""
from .base import AdapterDisabled, AdapterRateLimited, SourceAdapter
from .capabilities import (
    AdapterAccessMode,
    AdapterCapability,
    AdapterCost,
    AdapterMetadata,
    AdapterStatus,
    AdapterTier,
    RoleType,
)
from .registry import (
    ALL_ADAPTERS,
    all_adapter_classes,
    build_enabled_instances,
    discover_all,
    discover_entry_points,
    discover_in_tree,
    get_adapter_class,
    health_check_all,
    list_metadata,
    register_adapter,
)

__all__ = [
    "SourceAdapter",
    "AdapterDisabled",
    "AdapterRateLimited",
    "AdapterMetadata",
    "AdapterTier",
    "AdapterAccessMode",
    "AdapterCapability",
    "AdapterStatus",
    "AdapterCost",
    "RoleType",
    "register_adapter",
    "discover_all",
    "discover_in_tree",
    "discover_entry_points",
    "all_adapter_classes",
    "get_adapter_class",
    "list_metadata",
    "build_enabled_instances",
    "health_check_all",
    "ALL_ADAPTERS",
]
