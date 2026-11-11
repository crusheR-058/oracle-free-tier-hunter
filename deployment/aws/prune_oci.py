"""Removes OCI SDK services the hunter doesn't use, to fit Lambda's 250 MB limit.

Usage: python prune_oci.py <package_dir>
"""

from pathlib import Path
import re
import shutil
import sys

ROOTS = {"core", "identity", "limits", "auth", "_vendor", "pagination", "retry", "circuit_breaker"}
IMPORT = re.compile(
    r"^\s*(?:from\s+oci\.(\w+)|import\s+oci\.(\w+)|from\s+oci\s+import\s+([\w, ]+)"
    r"|from\s+(\.+)(\w*)\s+import\s+([\w, ]+))",
    re.M,
)


def imported_names(path: Path, oci_dir: Path) -> set:
    """Names this file imports from the top level of the oci package."""
    depth = len(path.relative_to(oci_dir).parts)
    names = set()
    for dotted, plain, absolute, dots, module, relative in IMPORT.findall(
        path.read_text(encoding="utf-8", errors="ignore")
    ):
        names |= {n for n in (dotted, plain) if n}
        names |= set(re.split(r"[,\s]+", absolute.strip()))
        # A relative import only reaches the top level when its dots match the file's depth.
        if dots and len(dots) == depth:
            names |= {module} if module else set(re.split(r"[,\s]+", relative.strip()))
    return names


def needed_services(oci_dir: Path) -> set:
    """Follows imports from ROOTS and the SDK's top-level modules."""
    dirs = {p.name for p in oci_dir.iterdir() if p.is_dir()}
    keep, queue = set(), list(ROOTS & dirs)
    # oci/__init__.py is skipped: services load on demand, and its fallback import lists all of them.
    files = [p for p in oci_dir.glob("*.py") if p.name != "__init__.py"]
    while files or queue:
        for name in queue:
            keep.add(name)
            files += list((oci_dir / name).rglob("*.py"))
        queue = []
        for path in files:
            for name in imported_names(path, oci_dir):
                if name in dirs and name not in keep and name not in queue:
                    queue.append(name)
        files = []
    return keep


def prune(package_dir: Path) -> set:
    oci_dir = package_dir / "oci"
    keep = needed_services(oci_dir)
    for child in oci_dir.iterdir():
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child)
    for cache in package_dir.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    return keep


if __name__ == "__main__":
    print("Kept OCI services:", ", ".join(sorted(prune(Path(sys.argv[1])))))
