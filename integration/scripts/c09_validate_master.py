"""Thin pipeline wrapper: run RUN\\deliverable\\validate_master.py so it appears in the same
c00..c09 run order as the rest of Phase C. The real invariants live in the deliverable itself
(validate_master.py is meant to travel WITH the CSV/parquet as a standalone file a downstream
consumer can run without this scripts/ folder) -- this wrapper just re-executes it in-process so
`python c09_validate_master.py` behaves identically to `python ../deliverable/validate_master.py`.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

from common_io import RUN  # noqa: E402

VALIDATE_SCRIPT = RUN / "deliverable" / "validate_master.py"


def main() -> None:
    ns = runpy.run_path(str(VALIDATE_SCRIPT), run_name="__not_main__")
    rc = ns["main"]()
    sys.exit(rc)


if __name__ == "__main__":
    main()
