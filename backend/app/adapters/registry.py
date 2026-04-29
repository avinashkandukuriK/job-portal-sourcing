"""Adapter registry — central catalog with auto-discovery.

Three ways an adapter gets registered:

1. **Decorator (in-tree).** Apply `@register_adapter` to the class. Simplest.

2. **Folder auto-discovery.** Any `.py` file under `app/adapters/sources/`
   importing a `SourceAdapter` subclass is loaded at startup. No manual list
   to maintain.

3. **Python entry-points (third-party plugins).** External packages can
   expose adapters via `pyproject.toml`:

       [project.entry-points."sourcing.adapters"]
       my_board = "my_pkg.adapters:MyBoardAdapter"

   Install the package and the adapter shows up — no edits to this repo.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from pathlib import Path
from typing import Iterator, Optional, Type

from .base import SourceAdapter
from .capabilities import AdapterMetadata, AdapterStatus, AdapterTier, RoleType

logger = logging.getLogger(__name__)

# In-process registry of adapter *classes* (not instances).
_REGISTRY: dict[str, Type[SourceAdapter]] = {}
_CORE_ADAPTER_MODULES = (
    "app.adapters.github",
    "app.adapters.stackoverflow",
)


# ----------------------- registration -----------------------

def register_adapter(cls: Type[SourceAdapter]) -> Type[SourceAdapter]:
    """Decorator: register an adapter class by its metadata.name."""
    if not hasattr(cls, "metadata"):
        raise ValueError(f"{cls.__name__} must define a `metadata: AdapterMetadata`")
    name = cls.metadata.name
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        logger.warning("Adapter %r re-registered (overwriting %s)", name, _REGISTRY[name])
    _REGISTRY[name] = cls
    logger.debug("Registered adapter: %s (%s)", name, cls.metadata.tier)
    return cls


# ----------------------- discovery -----------------------

def discover_in_tree() -> None:
    """Auto-import every module under app/adapters/sources/ so decorators run."""
    sources_path = Path(__file__).parent / "sources"
    if not sources_path.exists():
        return
    package = "app.adapters.sources"
    for mod in pkgutil.iter_modules([str(sources_path)]):
        if mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{package}.{mod.name}")
        except Exception as exc:  # noqa: BLE001 — never crash startup over a bad adapter
            logger.exception("Failed to import adapter module %s: %s", mod.name, exc)


def discover_entry_points() -> None:
    """Load adapters published by third-party packages via the
    'sourcing.adapters' entry-point group.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:  # py<3.10
        return

    try:
        eps = entry_points(group="sourcing.adapters")
    except TypeError:  # older importlib.metadata signature
        eps = entry_points().get("sourcing.adapters", [])  # type: ignore[attr-defined,arg-type]

    for ep in eps:
        try:
            cls = ep.load()
            if not issubclass(cls, SourceAdapter):
                logger.warning("Entry-point %s did not resolve to SourceAdapter", ep.name)
                continue
            register_adapter(cls)
            logger.info("Loaded plugin adapter via entry-point: %s", ep.name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load entry-point %s: %s", ep.name, exc)


def discover_all() -> None:
    """Run both discovery passes. Safe to call multiple times."""
    for module_name in _CORE_ADAPTER_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to import core adapter module %s: %s", module_name, exc)
    discover_in_tree()
    discover_entry_points()


# ----------------------- queries -----------------------

def all_adapter_classes() -> list[Type[SourceAdapter]]:
    return list(_REGISTRY.values())


def get_adapter_class(name: str) -> Type[SourceAdapter]:
    if name not in _REGISTRY:
        raise KeyError(f"No adapter registered with name {name!r}")
    return _REGISTRY[name]


def list_metadata(
    *,
    tier: Optional[AdapterTier] = None,
    role_type: Optional[RoleType] = None,
    region: Optional[str] = None,
) -> list[AdapterMetadata]:
    """Return metadata of registered adapters, optionally filtered.

    Used by the UI to render the source picker (Premium / Non-Premium tabs)
    and by the orchestrator to skip irrelevant sources for a given JD.
    """
    out: list[AdapterMetadata] = []
    for cls in _REGISTRY.values():
        m = cls.metadata
        if tier and m.tier != tier:
            continue
        if role_type and m.supported_role_types and role_type not in m.supported_role_types:
            continue
        if region and m.supported_regions and region not in m.supported_regions and "GLOBAL" not in m.supported_regions:
            continue
        out.append(m)
    return out


# ----------------------- instantiation -----------------------

async def build_enabled_instances(
    *,
    names: Optional[list[str]] = None,
    tier: Optional[AdapterTier] = None,
) -> list[SourceAdapter]:
    """Instantiate + setup adapters. Returns only those reporting `is_enabled() == True`.

    Pass `names` to constrain to specific adapters (UI source picker output).
    Pass `tier` to constrain to one tier (Premium vs Non-Premium runs).
    """
    selected: Iterator[Type[SourceAdapter]]
    if names:
        selected = (cls for n, cls in _REGISTRY.items() if n in names)
    else:
        selected = iter(_REGISTRY.values())

    instances: list[SourceAdapter] = []
    for cls in selected:
        if tier and cls.metadata.tier != tier:
            continue
        try:
            inst = cls()
            await inst.setup()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to instantiate adapter %s: %s", cls.metadata.name, exc)
            continue
        # `is_active()` combines code-level config readiness with the runtime
        # toggle state, so a paused or admin-disabled adapter is skipped here.
        if await inst.is_active():
            instances.append(inst)
        else:
            await inst.aclose()
            logger.info(
                "Skipping inactive adapter %s (%s)",
                cls.metadata.name,
                inst.disabled_reason() or "no reason given",
            )
    return instances


async def health_check_all() -> list[dict]:
    """Status report for every registered adapter — used by /api/adapters.

    Includes resolved status (DISABLED_USER, PAUSED, READY, etc.) and the raw
    toggle record so the UI can render switch state + reason + expiry.
    """
    out: list[dict] = []
    for cls in _REGISTRY.values():
        toggle = None
        try:
            inst = cls()
            status = await inst.status()
            toggle = inst.get_toggle()
            disabled_reason = inst.disabled_reason()
            await inst.aclose()
        except Exception as exc:  # noqa: BLE001
            status = AdapterStatus.DOWN
            disabled_reason = str(exc)
            logger.exception("Health check failed for %s: %s", cls.metadata.name, exc)
        out.append({
            "metadata": cls.metadata.model_dump(),
            "status": status.value,
            "toggle": toggle.model_dump(mode="json") if toggle else None,
            "disabled_reason": disabled_reason,
        })
    return out


# Convenience export for callers that just want the dict
ALL_ADAPTERS = _REGISTRY
