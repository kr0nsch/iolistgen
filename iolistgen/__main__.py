"""``python -m iolistgen`` — то же, что команда ``iolistgen``."""

from __future__ import annotations

import sys

from iolistgen.cli import main

if __name__ == "__main__":
    sys.exit(main())
