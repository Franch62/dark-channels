import shutil
from pathlib import Path

import pytest

from fabrica.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    shutil.copytree(ROOT / "channels", tmp_path / "channels")
    shutil.copytree(ROOT / "prompts", tmp_path / "prompts")
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'data' / 'test.sqlite'}",
        runs_dir=tmp_path / "runs", channels_dir=tmp_path / "channels",
        prompts_dir=tmp_path / "prompts", dry_run=True,
    )
