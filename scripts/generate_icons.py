"""Generate all app icon sizes from the canonical icon source."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from icon_assets import SOURCE_ICON_PATH, generate_icon_assets


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 扣舷 icon assets.")
    parser.add_argument("--source", default=str(SOURCE_ICON_PATH), help="source PNG path")
    parser.add_argument("--root", default=str(ROOT), help="project root")
    parser.add_argument("--include-current-dist", action="store_true", help="also sync dist/current assets")
    args = parser.parse_args()

    written = generate_icon_assets(
        source=args.source,
        root=args.root,
        include_current_dist=args.include_current_dist,
    )
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
