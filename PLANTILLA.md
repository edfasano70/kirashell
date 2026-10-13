# Plantilla: aplicación de escritorio con PyQt6

Guía de referencia para arrancar una nueva app de escritorio copiando la estructura y las
convenciones de `skill-pyqt6`. Reemplaza `kirashell` / `KiraShell` por el nombre real.

## 1. Estructura plana

```
kirashell/
├── main.py            # TODA la app: constantes, estilos, diálogos, MainWindow, main()
├── resources/         # assets
│   ├── logo.png       # 512x512, icono de la app y del "Acerca de"
│   ├── logo.svg       # fuente editable del logo (opcional)
│   └── icons/         # iconos de menú en SVG
├── src/               # vacío, reservado para módulos futuros
├── tests/
│   ├── conftest.py    # QApplication, offscreen, aísla el config
│   └── test_main.py
├── pyproject.toml     # ruff + pytest + metadatos
└── README.md
```

Reglas de oro:

- Todo el código inicial vive en `main.py` (raíz). Es un solo archivo, fácil de leer.
- Los recursos van en `resources/` (raíz), no dentro de paquetes.
- `src/` queda vacío hasta que necesites separar módulos.
- Nunca construyas widgets al importar: permite importar `main` sin abrir ventana.
- Sin entorno virtual: las deps viven en `~/.local`.

## 2. Setup

**Sin entorno virtual.** Instala las dependencias en tu usuario:

```bash
python3 -m pip install --user --break-system-packages PyQt6 pytest ruff
```

`--user` escribe en `~/.local` y `--break-system-packages` es necesario en Debian/Ubuntu
(regla PEP 668). No hace falta instalar el proyecto: `python main.py` y `pytest` funcionan
directamente desde la raíz.

## 3. `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "kirashell"
version = "0.1.0"
description = "Aplicación de escritorio PyQt6"
readme = "README.md"
requires-python = ">=3.10"
dependencies = ["PyQt6>=6.6"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.setuptools]
py-modules = ["main"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py310"
extend-exclude = ["*.md"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

`extend-exclude = ["*.md"]` evita que ruff reformatee los bloques de código de la
documentación.

## 4. Esqueleto de `main.py`

Un solo archivo, en este orden:

```python
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
)

PROGRAM_NAME = "kirashell"
PROGRAM_VERSION = "0.1.0"
PROGRAM_DESCRIPTION = "Aplicación de escritorio PyQt6"

RESOURCES_DIR = Path(__file__).resolve().parent / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
LOGO_FILE = RESOURCES_DIR / "logo.png"

CONFIG_FILE = Path(__file__).resolve().parent / "config.xml"

DARK_STYLE = ""  # ver sección 7
```

Y al final del archivo:

```python
def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(_logo_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

## 5. Ventana principal y menús

```python
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.dark_mode = False
        self.setWindowTitle(PROGRAM_NAME)
        self.setWindowIcon(_logo_icon())
        self.resize(480, 320)
        self._build_menus()
        self._load_preferences()
        self.statusBar().showMessage("Listo")

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Archivo")
        exit_action = QAction(_icon("exit_to_app"), "Salir", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu("Ver")
        self.dark_mode_action = QAction(_icon("brightness_6"), "Alternar modo oscuro/claro", self)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        view_menu.addAction(self.dark_mode_action)

        help_menu = menu_bar.addMenu("Ayuda")
        instructions_action = QAction(_icon("help"), "Instrucciones", self)
        instructions_action.setShortcut("F1")
        instructions_action.triggered.connect(self.show_instructions)
        help_menu.addAction(instructions_action)

        about_action = QAction(_icon("info"), "Acerca de...", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
```

Diálogos: `AboutDialog` y `HelpDialog` son `QDialog` con `QVBoxLayout`, un `QLabel` con
`setWordWrap(True)`, un `QPushButton("Cerrar")` que llama a `accept()`, y reciben `dark_mode`
para aplicar el tema. Oculta el botón de ayuda contextual:

```python
self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
```

## 6. Persistencia en `config.xml`

Ubicación: `config.xml` en la raíz del proyecto (ignorado por git).
Guarda geometría/posición de la ventana y el tema.

```python
    def _apply_dark_mode(self, enabled: bool) -> None:
        self.dark_mode = enabled
        self.setStyleSheet(DARK_STYLE if enabled else "")

    def _load_preferences(self) -> None:
        if not CONFIG_FILE.exists():
            self._center()
            return
        try:
            root = ET.parse(CONFIG_FILE).getroot()
        except ET.ParseError:
            self._center()
            return

        window = root.find("window")
        if window is None:
            self._center()
        else:
            try:
                self.resize(int(window.findtext("width")), int(window.findtext("height")))
                self.move(int(window.findtext("x")), int(window.findtext("y")))
            except (TypeError, ValueError):
                self._center()

        dark_mode = root.findtext("settings/dark_mode")
        if dark_mode is not None:
            self._apply_dark_mode(dark_mode.lower() == "true")

    def _save_preferences(self) -> None:
        root = ET.Element(PROGRAM_NAME)
        window = ET.SubElement(root, "window")
        ET.SubElement(window, "x").text = str(self.x())
        ET.SubElement(window, "y").text = str(self.y())
        ET.SubElement(window, "width").text = str(self.width())
        ET.SubElement(window, "height").text = str(self.height())
        settings = ET.SubElement(root, "settings")
        ET.SubElement(settings, "dark_mode").text = str(self.dark_mode).lower()
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(CONFIG_FILE, encoding="utf-8", xml_declaration=True)

    def closeEvent(self, event) -> None:
        self._save_preferences()
        event.accept()
```

XML resultante:

```xml
<?xml version='1.0' encoding='utf-8'?>
<kirashell>
  <window>
    <x>160</x>
    <y>240</y>
    <width>480</width>
    <height>320</height>
  </window>
  <settings>
    <dark_mode>true</dark_mode>
  </settings>
</kirashell>
```

Centrar cuando no hay config:

```python
    def _center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())
```

## 7. Tema claro/oscuro

QSS oscuro con acento naranja; el tema claro es hoja vacía (`""` = estilo nativo).

```python
DARK_STYLE = """
    QMainWindow, QWidget, QDialog { background-color: #1e1e1e; color: #e0e0e0; }
    QMenuBar { background-color: #2d2d2d; color: #e0e0e0; }
    QMenuBar::item { padding: 4px 8px; }
    QMenuBar::item:selected { background-color: #3d3d3d; }
    QMenu { background-color: #2d2d2d; color: #e0e0e0; }
    QMenu::item:selected { background-color: #FF9800; color: #1e1e1e; }
    QLabel { color: #e0e0e0; }
    QPushButton { background-color: #3d3d3d; border: 1px solid #555;
        border-radius: 3px; padding: 4px 8px; color: #e0e0e0; }
    QPushButton:hover { background-color: #4d4d4d; }
"""
```

El tema se aplica con `setStyleSheet` en la ventana y se pasa a los diálogos por constructor
(`HelpDialog(self, dark_mode=self.dark_mode)`), no por singletons.

## 8. Iconos y recursos

- Iconos de menú: Material Design en SVG, `#FF9800`, en `resources/icons/`.
- Logo: PNG **512×512** (`resources/logo.png`) usado en `MainWindow.setWindowIcon`,
  en `QApplication.setWindowIcon` y dentro de `AboutDialog` (escalado a 120 px con
  `Qt.AspectRatioMode.KeepAspectRatio`).
- Carga tolerante a fallos:

```python
def _icon(name: str) -> QIcon:
    path = ICONS_DIR / f"{name}.svg"
    return QIcon(str(path)) if path.is_file() else QIcon()


def _logo_icon() -> QIcon:
    return QIcon(str(LOGO_FILE)) if LOGO_FILE.is_file() else QIcon()
```

- Rasterizar un SVG descargado a PNG 512×512 con QtSvg:

```python
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

app = QGuiApplication(sys.argv[:1])
renderer = QSvgRenderer("logo.svg")
image = QImage(512, 512, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
renderer.render(painter)
painter.end()
image.save("logo.png")
```

## 9. Tests

`tests/conftest.py`: plataforma offscreen, fixture `qapp` y aislamiento del config.

```python
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
```

El `conftest` agrega la raíz del repo a `sys.path` para poder `import main`. Buenas prácticas:

- Pide `qapp` en cualquier test que construya un widget.
- No uses `pytest-qt`/`qtbot`: llama directamente (`button.click()`).
- Verifica estructura de menús, iconos no nulos, tema y persistencia del XML.
- Nunca toques el config real: la fixture autouse lo redirige a `tmp_path`.

Ejemplo en `tests/test_main.py`:

```python
import main
from main import MainWindow


def test_preferences_persisted(qapp):
    window = MainWindow()
    window.toggle_dark_mode()
    window._save_preferences()

    root = ET.parse(main.CONFIG_FILE).getroot()
    assert root.findtext("settings/dark_mode") == "true"

    restored = MainWindow()
    assert restored.dark_mode is True
```

## 10. Comandos

```bash
python main.py                                      # ejecutar
pytest                                              # toda la suite
pytest tests/test_main.py::test_menus               # un test
ruff check .                                        # lint (E,F,I,UP,B; imports ordenados)
ruff format .                                       # formato (line-length 100)
```

Siempre ejecuta `pytest` tras cambiar el código y `ruff check .` antes de terminar.

## 11. Gotchas de PyQt6 (distinto de PyQt5)

- Enums con ámbito completo: `Qt.AlignmentFlag.AlignCenter`, `Qt.WindowType.*`,
  `QSizePolicy.Policy.*`.
- Señales igual que antes (`.clicked.connect(...)`), pero `app.exec()` reemplaza `exec_()`.
- `QAction` vive en `PyQt6.QtGui`; `QSvgRenderer` en `PyQt6.QtSvg`.
- No construyas UI en tiempo de import para que los tests importen `main` sin abrir ventana.
- Los recursos se resuelven con `Path(__file__).resolve().parent / "resources"`, así que
  ejecuta desde la raíz del repo.

## 12. Checklist para una nueva app

1. Copia la estructura de la sección 1 y renombra `kirashell` / `KiraShell`.
2. Ajusta `pyproject.toml` (nombre, descripción).
3. Instala deps: `python3 -m pip install --user --break-system-packages PyQt6 pytest ruff`.
4. Escribe `main.py` con constantes, estilos, diálogos, `MainWindow` y `main()`.
5. Agrega recursos (logo 512×512 e iconos SVG naranja) en `resources/`.
6. Implementa `config.xml` para geometría y preferencias.
7. Copia `conftest.py` y escribe `tests/test_main.py`.
8. Verifica: `pytest` verde y `ruff check .` / `ruff format .` limpios.
