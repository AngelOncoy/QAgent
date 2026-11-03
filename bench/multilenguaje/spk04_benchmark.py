"""Script de benchmark para SPK-04 (ADR-009).

Punto de entrada compatible que delega en `medir_parsers_spk04.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

BENCH_MULTI_DIR = Path(__file__).resolve().parent
if str(BENCH_MULTI_DIR) not in sys.path:
    sys.path.insert(0, str(BENCH_MULTI_DIR))

from medir_parsers_spk04 import main

if __name__ == "__main__":
    main()
