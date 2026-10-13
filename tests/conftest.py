import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CONFIG_FILE", tmp_path / "config.xml")
    monkeypatch.setattr(main, "SERVERS_FILE", tmp_path / "servers.json")
