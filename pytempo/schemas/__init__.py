"""Internal schema infrastructure. NOT part of the public API.

The registry is the map of the catalogue: one record per indicator, with the
shape of its dimensions, its family and its estimated cost. The search filters
rest on it, and so does the fetch plan.

Used from a development shell, not from pytempo directly:
    from pytempo import schemas
    schemas.build_registry()
    schemas.report()
"""
from .build import (REGISTRY_PATH, REGISTRY_VERSION, build_registry,
                    load_registry, plan_for, refresh_plans, registry_as_index,
                    report)
from .classify import FAMILIES, classify
from .validate import spot_check_list, validate

__all__ = [
    "build_registry", "report", "load_registry", "registry_as_index",
    "classify", "FAMILIES", "REGISTRY_PATH", "REGISTRY_VERSION",
    "plan_for", "refresh_plans", "validate", "spot_check_list",
]
