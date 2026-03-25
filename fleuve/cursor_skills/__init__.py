"""Cursor Agent Skills for Fleuve (bundled markdown).

Install into a project with ``fleuve cursor-skills install`` so Cursor loads them
from ``.cursor/skills/``. Skills are also available under the package directory
for inspection or custom tooling.
"""

from pathlib import Path


def bundled_skills_dir() -> Path:
    """Directory containing skill subfolders (fleuve-workflow-authoring, etc.)."""
    return Path(__file__).resolve().parent
