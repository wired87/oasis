from __future__ import annotations

import subprocess
from pathlib import Path


BRAIN_REPO_URL = "https://github.com/wired87/brain.git"


def ensure_brain_repo(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or Path(__file__).resolve().parent)
    brain_dir = root / "brain"
    if brain_dir.exists() and not brain_dir.is_dir():
        raise NotADirectoryError(f"{brain_dir} exists but is not a directory.")
    if (brain_dir / ".git").exists():
        return brain_dir
    if brain_dir.exists():
        raise RuntimeError(
            f"{brain_dir} already exists but is not a git repository. Remove it and retry."
        )

    try:
        subprocess.run(
            ["git", "clone", BRAIN_REPO_URL, str(brain_dir)],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to clone brain repository from {BRAIN_REPO_URL}: {exc}") from exc
    return brain_dir


if __name__ == "__main__":
    target = ensure_brain_repo()
    print(f"Brain repository ready at {target}")
