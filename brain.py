from __future__ import annotations

import subprocess
from pathlib import Path


BRAIN_REPO_URL = "https://github.com/wired87/brain.git"


def ensure_brain_repo(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or Path(__file__).resolve().parent)
    brain_dir = root / "brain"
    if brain_dir.exists():
        return brain_dir

    subprocess.run(
        ["git", "clone", BRAIN_REPO_URL, str(brain_dir)],
        check=True,
    )
    return brain_dir


if __name__ == "__main__":
    target = ensure_brain_repo()
    print(f"Brain repository ready at {target}")
