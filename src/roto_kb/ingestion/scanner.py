from __future__ import annotations

from pathlib import Path

from ..config import PathPolicy
from .parsers import source_from_path


# Include engineering example source (.py): FEniTop beam_3d/topopt carry parameter truth such as vol_frac.
SUPPORTED = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf", ".ttl", ".rdf", ".owl", ".jsonl", ".py"}


def infer_domain(relative: str) -> str:
    text = relative.replace("\\", "/").lower()
    if "fenitop" in text:
        return "fenitop-examples"
    if any(name in text for name in ("gmsh", "meshio", "trimesh", "pyvista", "cadquery")):
        return "mesh-geometry"
    if any(name in text for name in ("dolfinx", "jax-fem", "mfem", "ngsolve", "moose")):
        return "fem-solvers"
    if "/papers/" in text or text.startswith("papers/"):
        return "topopt-theory"
    if "qudt" in text:
        return "units-ontology"
    if "iof-core" in text or "/iof/" in text:
        return "industrial-ontology"
    if "/w3c/" in text or text.startswith("ontologies/w3c"):
        return "provenance-vocab"
    if "roto-domain-seed" in text or "/graph/seeds/" in text:
        return "roto-domain"
    return "general"


def scan_sources(root: str | Path, *, domain: str | None = None, policy: PathPolicy | None = None, allowed_paths: set[Path] | None = None):
    root = Path(root).resolve()
    policy = policy or PathPolicy(root)
    policy.resolve(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in SUPPORTED:
            if allowed_paths is not None and path.resolve() not in allowed_paths:
                continue
            relative = path.resolve().relative_to(root).as_posix()
            resolved_domain = domain or infer_domain(relative)
            yield source_from_path(path, root=root, domain=resolved_domain)
