#!/usr/bin/env python3
"""Build the Fleuve UI frontend and copy to fleuve/ui/frontend_dist for packaging.

Run from repo root: python scripts/build_ui.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_SRC = REPO_ROOT / "fleuve" / "templates" / "ui_addon" / "ui" / "frontend"
FRONTEND_DIST_SRC = FRONTEND_SRC / "dist"
FRONTEND_DIST_DST = REPO_ROOT / "fleuve" / "ui" / "frontend_dist"


def main():
    if not FRONTEND_SRC.exists():
        print(f"Error: Frontend source not found at {FRONTEND_SRC}", file=sys.stderr)
        sys.exit(1)

    print("Installing npm dependencies...")
    install = subprocess.run(
        ["npm", "install"],
        cwd=FRONTEND_SRC,
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        print(f"npm install failed:\n{install.stderr}", file=sys.stderr)
        sys.exit(1)

    print("Building frontend...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=FRONTEND_SRC,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"npm build failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    if not FRONTEND_DIST_SRC.exists() or not (FRONTEND_DIST_SRC / "index.html").exists():
        print(f"Error: Build output not found at {FRONTEND_DIST_SRC}", file=sys.stderr)
        sys.exit(1)

    print(f"Copying to {FRONTEND_DIST_DST}...")
    FRONTEND_DIST_DST.mkdir(parents=True, exist_ok=True)
    for item in FRONTEND_DIST_SRC.iterdir():
        dst = FRONTEND_DIST_DST / item.name
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)

    print("Done. fleuve/ui/frontend_dist is ready for packaging.")


if __name__ == "__main__":
    main()
