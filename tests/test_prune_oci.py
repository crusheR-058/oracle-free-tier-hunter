"""The Lambda package must keep every OCI service the kept code imports, and only those."""

import importlib.util
from pathlib import Path


def load_prune():
    path = Path(__file__).parent.parent / "deployment" / "aws" / "prune_oci.py"
    spec = importlib.util.spec_from_file_location("prune_oci", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_keeps_real_imports_and_removes_the_rest(tmp_path):
    modules = {
        "__init__.py": "from . import fallback_listed\n",
        "base.py": "from . import top_level_relative\n",
        "core/client.py": "from oci import retry, absolute_list\nimport oci.dotted\nfrom oci.from_dotted.x import y\n"
        "from . import own_module\n",
        "pagination/utils.py": "from .. import relative_one, relative_two\n",
        "relative_two/client.py": "from ..chained import x\n",
    }
    wanted = ["retry", "absolute_list", "dotted", "from_dotted", "relative_one", "relative_two", "chained",
              "top_level_relative", "core", "pagination"]
    unwanted = ["fallback_listed", "own_module", "unused"]
    for name in wanted + unwanted:
        (tmp_path / "oci" / name).mkdir(parents=True)
    for relative, text in modules.items():
        (tmp_path / "oci" / relative).write_text(text)

    load_prune().prune(tmp_path)

    kept = {p.name for p in (tmp_path / "oci").iterdir() if p.is_dir()}
    assert kept == set(wanted)
