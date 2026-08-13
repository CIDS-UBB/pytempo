"""Infrastructura internă de scheme. NU face parte din API-ul public.

Registrul e harta catalogului: o fișă per indicator, cu forma dimensiunilor,
familia și costul estimat. Pe el se sprijină filtrele din search, iar mai
târziu planul de extragere.

Se folosește din dezvoltare, nu din pytempo direct:
    from pytempo import schemas
    schemas.build_registry()
    schemas.report()
"""
from .build import (REGISTRY_PATH, REGISTRY_VERSION, build_registry,
                    load_registry, registry_as_index, report)
from .classify import FAMILIES, classify

__all__ = [
    "build_registry", "report", "load_registry", "registry_as_index",
    "classify", "FAMILIES", "REGISTRY_PATH", "REGISTRY_VERSION",
]
