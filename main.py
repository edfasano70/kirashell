from __future__ import annotations

import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

PROGRAM_NAME = "kirashell"
PROGRAM_TITLE = "KiraShell"
PROGRAM_VERSION = "0.2.0"
PROGRAM_DESCRIPTION = "Facilita la conexión SSH a múltiples servidores"

RESOURCES_DIR = Path(__file__).resolve().parent / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
LOGO_FILE = RESOURCES_DIR / "logo.png"

CONFIG_DIR = Path.home() / ".config" / "kirashell"
CONFIG_FILE = CONFIG_DIR / "config.xml"
SERVERS_FILE = CONFIG_DIR / "servers.json"

DEFAULT_PORT = "22"

# Terminales soportadas: (comando, bandera para ejecutar el resto como programa + args)
_TERMINALS = (
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("tilix", ["-e"]),
    ("alacritty", ["-e"]),
    ("kitty", ["-e"]),
    ("xterm", ["-e"]),
    ("x-terminal-emulator", ["-e"]),
)

DARK_STYLE = """
    QMainWindow, QWidget, QDialog { background-color: #1e1e1e; color: #e0e0e0; }
    QMenuBar { background-color: #2d2d2d; color: #e0e0e0; }
    QMenuBar::item { padding: 4px 8px; }
    QMenuBar::item:selected { background-color: #3d3d3d; }
    QMenu { background-color: #2d2d2d; color: #e0e0e0; }
    QMenu::item:selected { background-color: #FF9800; color: #1e1e1e; }
    QLabel { color: #e0e0e0; }
    QLineEdit { background-color: #2d2d2d; border: 1px solid #555;
        border-radius: 3px; padding: 4px; color: #e0e0e0; }
    QCheckBox { color: #e0e0e0; }
    QPushButton { background-color: #3d3d3d; border: 1px solid #555;
        border-radius: 3px; padding: 4px 8px; color: #e0e0e0; }
    QPushButton:hover { background-color: #4d4d4d; }
    QPushButton#connectButton { background-color: #FF9800; border: none;
        color: #1e1e1e; font-weight: bold; }
    QPushButton#connectButton:hover { background-color: #FFB74D; }
    #serverCard { background-color: #2d2d2d; border: 1px solid #444;
        border-radius: 6px; }
"""


def _icon(name: str) -> QIcon:
    path = ICONS_DIR / f"{name}.svg"
    if path.is_file():
        return QIcon(str(path))
    return QIcon()


def _logo_icon() -> QIcon:
    if LOGO_FILE.is_file():
        return QIcon(str(LOGO_FILE))
    return QIcon()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.strip().lower()).strip("-")
    return slug or "servidor"


def _encode_password(password: str) -> str:
    """Obfusca la contraseña antes de guardarla (no es cifrado real)."""
    return base64.b64encode(password.encode("utf-8")).decode("ascii")


def _decode_password(encoded: str) -> str:
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def _format_target(info: dict) -> str:
    """Devuelve 'usuario@host' (o solo host/usuario) para mostrar en la tarjeta."""
    user = (info.get("username") or "").strip()
    host = (info.get("host") or "").strip()
    if user and host:
        return f"{user}@{host}"
    return host or user


def load_servers() -> dict[str, dict]:
    """Devuelve los servidores guardados, con la contraseña ya descodificada."""
    if not SERVERS_FILE.exists():
        return {}
    try:
        data = json.loads(SERVERS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    servers: dict[str, dict] = {}
    for server_id, info in data.items():
        if not isinstance(info, dict):
            continue
        entry = dict(info)
        entry["password"] = _decode_password(str(entry.get("password", "")))
        servers[server_id] = entry
    return servers


def save_servers(servers: dict[str, dict]) -> None:
    """Guarda los servidores en JSON, codificando la contraseña y protegiendo el archivo."""
    data: dict[str, dict] = {}
    for server_id, info in servers.items():
        entry = dict(info)
        entry["password"] = _encode_password(str(entry.get("password", "")))
        data[server_id] = entry

    SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERVERS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        os.chmod(SERVERS_FILE, 0o600)
    except OSError:
        pass


def create_server(
    label: str,
    username: str,
    password: str,
    host: str,
    port: str = DEFAULT_PORT,
    overwrite: bool = False,
    previous_id: str | None = None,
) -> str:
    """Añade (o actualiza, si se da ``previous_id``) un servidor y devuelve su id."""
    label = label.strip()
    if not label:
        raise ValueError("La etiqueta no puede estar vacía")

    username = username.strip()
    if not username:
        raise ValueError("El usuario no puede estar vacío")

    host = host.strip()
    if not host:
        raise ValueError("El servidor no puede estar vacío")

    port = (port or DEFAULT_PORT).strip()
    try:
        port_number = int(port)
        if not 1 <= port_number <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("El puerto debe ser un número entre 1 y 65535") from None

    server_id = _slugify(label)
    is_same_file = previous_id is not None and server_id == previous_id

    servers = load_servers()
    if server_id in servers and not is_same_file and not overwrite:
        raise FileExistsError(server_id)

    if previous_id is not None and previous_id != server_id:
        servers.pop(previous_id, None)

    servers[server_id] = {
        "label": label,
        "username": username,
        "password": password,
        "host": host,
        "port": str(port_number),
    }
    save_servers(servers)
    return server_id


def delete_server(server_id: str) -> None:
    servers = load_servers()
    servers.pop(server_id, None)
    save_servers(servers)


def import_servers(xml_path: str) -> int:
    """Importa servidores desde un archivo XML y devuelve cuántos se importaron.

    Formato esperado::

        <servers>
          <server>
            <label>Producción</label>
            <username>root</username>
            <password>clave</password>
            <host>10.0.0.5</host>
            <port>22</port>
          </server>
        </servers>

    Las entradas que no superen la validación (etiqueta/usuario/host/puerto)
    se omiten silenciosamente.
    """
    root = ET.parse(xml_path).getroot()
    count = 0
    for server_elem in root.findall("server"):
        label = (server_elem.findtext("label") or "").strip()
        username = (server_elem.findtext("username") or "").strip()
        password = server_elem.findtext("password") or ""
        host = (server_elem.findtext("host") or "").strip()
        port = (server_elem.findtext("port") or DEFAULT_PORT).strip()
        if not label or not host:
            continue
        try:
            create_server(label, username, password, host, port, overwrite=True)
            count += 1
        except ValueError:
            continue
    return count


def export_servers(xml_path: str) -> int:
    """Exporta los servidores guardados a un archivo XML y devuelve cuántos se exportaron."""
    servers = load_servers()
    root = ET.Element("servers")
    for info in servers.values():
        server_elem = ET.SubElement(root, "server")
        ET.SubElement(server_elem, "label").text = info.get("label", "")
        ET.SubElement(server_elem, "username").text = info.get("username", "")
        ET.SubElement(server_elem, "password").text = info.get("password", "")
        ET.SubElement(server_elem, "host").text = info.get("host", "")
        ET.SubElement(server_elem, "port").text = info.get("port", DEFAULT_PORT)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return len(servers)


def _ssh_shell(info: dict) -> str:
    """Construye la línea de comandos SSH a ejecutar en el terminal."""
    password = info.get("password", "")
    username = info.get("username", "")
    host = info.get("host", "")
    port = info.get("port", "")

    if password and shutil.which("sshpass"):
        command = f"sshpass -p {shlex.quote(password)} ssh"
    else:
        command = "ssh"

    command += " -o StrictHostKeyChecking=accept-new"
    if port and port != DEFAULT_PORT:
        command += f" -p {port}"
    remote = f"{username}@{host}" if username else host
    command += f" {shlex.quote(remote)}"
    return command


def _terminal_launcher() -> list[str] | None:
    """Devuelve [terminal, bandera] del primer emulador de terminal disponible."""
    for name, flag in _TERMINALS:
        path = shutil.which(name)
        if path:
            return [path, *flag]
    return None


def open_ssh(info: dict) -> tuple[bool, str]:
    """Abre una consola SSH al servidor en un emulador de terminal.

    Devuelve ``(ok, mensaje)``: ``ok`` es False si no se pudo abrir.
    """
    launcher = _terminal_launcher()
    if launcher is None:
        return False, (
            "No se encontró ningún emulador de terminal "
            "(xterm, xfce4-terminal, gnome-terminal, konsole...)."
        )

    shell = _ssh_shell(info)
    shell += "; echo; read -r -p 'Conexión cerrada. Pulsa Intro para cerrar...'"

    try:
        subprocess.Popen(
            [*launcher, "bash", "-lc", shell],
            start_new_session=True,
        )
    except OSError as error:
        return False, f"No se pudo abrir el terminal:\n{error}"
    return True, ""


class AboutDialog(QDialog):
    """Diálogo modal 'Acerca de'."""

    def __init__(self, parent=None, dark_mode: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Acerca de")
        self.setWindowIcon(_logo_icon())
        self.setFixedSize(300, 320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(15, 15, 15, 15)

        pixmap = QPixmap(str(LOGO_FILE))
        if not pixmap.isNull():
            logo_label = QLabel()
            logo_label.setPixmap(
                pixmap.scaled(
                    120,
                    120,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)

        name_label = QLabel(PROGRAM_TITLE)
        name_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        version_label = QLabel(f"v{PROGRAM_VERSION}")
        version_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        credits_label = QLabel("Programado por @EdFasano70")
        credits_label.setFont(QFont("Arial", 8))
        credits_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(credits_label)

        desc_label = QLabel(PROGRAM_DESCRIPTION)
        desc_label.setFont(QFont("Arial", 9))
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        close_btn = QPushButton("Cerrar")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        if dark_mode:
            self.setStyleSheet(DARK_STYLE)


class HelpDialog(QDialog):
    """Diálogo modal con las instrucciones de uso."""

    def __init__(self, parent=None, dark_mode: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Instrucciones")
        self.setWindowIcon(_logo_icon())
        self.setFixedSize(420, 280)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel(f"Cómo usar {PROGRAM_TITLE}")
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)

        instructions = (
            "1. Usa <b>Archivo &rarr; Nuevo servidor...</b> para añadir un servidor SSH.<br>"
            "2. Pulsa <b>Conectar</b> en una tarjeta para abrir una consola SSH.<br>"
            "3. Usa <b>Editar</b> / <b>Eliminar</b> para modificar o quitar servidores.<br>"
            "4. Usa <b>Archivo &rarr; Importar/Exportar servidores...</b> para respaldar<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;la lista en formato XML.<br>"
            "5. Usa <b>Ver &rarr; Alternar modo oscuro/claro</b> para cambiar el tema.<br>"
            "6. Consulta <b>Ayuda &rarr; Acerca de...</b> para ver la versión."
        )
        text_label = QLabel(instructions)
        text_label.setFont(QFont("Arial", 9))
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        layout.addStretch()

        close_btn = QPushButton("Cerrar")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        if dark_mode:
            self.setStyleSheet(DARK_STYLE)


class ServerDialog(QDialog):
    """Formulario para crear o editar un servidor SSH."""

    def __init__(
        self,
        parent=None,
        dark_mode: bool = False,
        server_id: str | None = None,
        info: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.server_id = server_id
        editing = server_id is not None and info is not None
        self.setWindowTitle("Editar servidor" if editing else "Nuevo servidor")
        self.setWindowIcon(_logo_icon())
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        form = QFormLayout()

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Producción")
        form.addRow("Etiqueta:", self.label_edit)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("root")
        form.addRow("Usuario:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("(opcional: se usará clave SSH o se pedirá)")
        form.addRow("Contraseña:", self._with_show_password(self.password_edit))

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("192.168.1.10 o servidor.example.com")
        form.addRow("Servidor (IP o nombre):", self.host_edit)

        self.port_edit = QLineEdit(DEFAULT_PORT)
        self.port_edit.setMaximumWidth(90)
        form.addRow("Puerto:", self.port_edit)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setFixedWidth(90)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        save_btn = QPushButton("Guardar" if editing else "Crear")
        save_btn.setFixedWidth(90)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        if editing:
            self._apply_info(info)

        if dark_mode:
            self.setStyleSheet(DARK_STYLE)

    def _with_show_password(self, field: QLineEdit) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field)
        show = QCheckBox("Mostrar")
        show.toggled.connect(
            lambda checked: field.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(show)
        return container

    def _apply_info(self, info: dict) -> None:
        self.label_edit.setText(info.get("label", ""))
        self.username_edit.setText(info.get("username", ""))
        self.password_edit.setText(info.get("password", ""))
        self.host_edit.setText(info.get("host", ""))
        self.port_edit.setText(info.get("port", DEFAULT_PORT))

    def _save(self) -> None:
        label = self.label_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip() or DEFAULT_PORT

        if not label:
            QMessageBox.warning(self, "Datos incompletos", "La etiqueta no puede estar vacía.")
            return
        if not username:
            QMessageBox.warning(self, "Datos incompletos", "El usuario no puede estar vacío.")
            return
        if not host:
            QMessageBox.warning(self, "Datos incompletos", "Indica el servidor (IP o nombre).")
            return

        new_id = _slugify(label)
        is_same = self.server_id is not None and new_id == self.server_id
        overwrite = False
        if new_id in load_servers() and not is_same:
            confirm = QMessageBox.question(
                self,
                "Ya existe",
                f"Ya existe un servidor con la etiqueta '{label}'.\n¿Quieres sobrescribirlo?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            overwrite = True

        try:
            create_server(
                label,
                username,
                password,
                host,
                port,
                overwrite=overwrite,
                previous_id=self.server_id,
            )
        except (ValueError, OSError) as error:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el servidor:\n{error}")
            return

        QMessageBox.information(self, "Servidor guardado", f"Se guardó '{label}'.")
        self.accept()


class ServerCard(QFrame):
    """Tarjeta que representa un servidor SSH guardado."""

    def __init__(self, server_id: str, info: dict, on_connect, on_edit, on_delete) -> None:
        super().__init__()
        self.server_id = server_id
        self.setObjectName("serverCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(_icon("connect").pixmap(48, 48))
        icon_label.setFixedSize(48, 48)
        layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        name_label = QLabel(info.get("label", server_id))
        name_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        text_layout.addWidget(name_label)

        target_label = QLabel(_format_target(info))
        target_label.setFont(QFont("Arial", 9))
        text_layout.addWidget(target_label)

        labels = [name_label, target_label]
        port = (info.get("port") or "").strip()
        if port and port != DEFAULT_PORT:
            port_label = QLabel(f"Puerto: {port}")
            port_label.setFont(QFont("Arial", 8))
            text_layout.addWidget(port_label)
            labels.append(port_label)

        for label in labels:
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setToolTip(label.text())

        layout.addLayout(text_layout, 1)

        connect_btn = QPushButton(_icon("connect"), "Conectar")
        connect_btn.setObjectName("connectButton")
        connect_btn.clicked.connect(lambda: on_connect(self.server_id))
        layout.addWidget(connect_btn)

        edit_btn = QPushButton(_icon("edit"), "Editar")
        edit_btn.clicked.connect(lambda: on_edit(self.server_id))
        layout.addWidget(edit_btn)

        delete_btn = QPushButton(_icon("delete"), "Eliminar")
        delete_btn.clicked.connect(lambda: on_delete(self.server_id))
        layout.addWidget(delete_btn)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.dark_mode = False
        self.setWindowTitle(PROGRAM_TITLE)
        self.setWindowIcon(_logo_icon())
        self.resize(560, 380)
        self._build_menus()
        self._build_central()
        self._load_preferences()
        self.statusBar().showMessage("Listo")

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Archivo")
        new_action = QAction(_icon("add"), "Nuevo servidor...", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.show_server_dialog)
        file_menu.addAction(new_action)
        file_menu.addSeparator()
        import_action = QAction(_icon("upload"), "Importar servidores...", self)
        import_action.triggered.connect(self.show_import_servers)
        file_menu.addAction(import_action)
        export_action = QAction(_icon("download"), "Exportar servidores...", self)
        export_action.triggered.connect(self.show_export_servers)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
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

    def _build_central(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Servidores SSH")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()
        create_btn = QPushButton(_icon("add"), "Nuevo servidor...")
        create_btn.clicked.connect(self.show_server_dialog)
        header.addWidget(create_btn)
        outer.addLayout(header)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.cards_container)
        outer.addWidget(self.scroll)

        self.setCentralWidget(central)
        self._refresh_cards()

    def _refresh_cards(self) -> None:
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        servers = load_servers()
        if not servers:
            empty = QLabel("Todavía no has añadido ningún servidor SSH.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.insertWidget(0, empty)
            return

        for server_id, info in servers.items():
            card = ServerCard(
                server_id,
                info,
                self._connect_server,
                self._edit_server,
                self._delete_server,
            )
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def show_import_servers(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar servidores",
            filter="XML (*.xml)",
        )
        if not path:
            return
        try:
            count = import_servers(path)
        except (OSError, ET.ParseError) as error:
            QMessageBox.critical(self, "Error", f"No se pudo importar:\n{error}")
            return
        self._refresh_cards()
        QMessageBox.information(
            self, "Importación completada", f"Se importaron {count} servidor(es)."
        )

    def show_export_servers(self) -> None:
        servers = load_servers()
        if not servers:
            QMessageBox.information(self, "Nada que exportar", "No hay servidores para exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar servidores",
            "servidores.xml",
            filter="XML (*.xml)",
        )
        if not path:
            return
        try:
            count = export_servers(path)
        except OSError as error:
            QMessageBox.critical(self, "Error", f"No se pudo exportar:\n{error}")
            return
        QMessageBox.information(
            self,
            "Exportación completada",
            f"Se exportaron {count} servidor(es) a:\n{path}",
        )

    def _edit_server(self, server_id: str) -> None:
        info = load_servers().get(server_id)
        if info is None:
            self._refresh_cards()
            return
        dialog = ServerDialog(self, dark_mode=self.dark_mode, server_id=server_id, info=info)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_cards()

    def _delete_server(self, server_id: str) -> None:
        info = load_servers().get(server_id, {})
        label = info.get("label", server_id)
        confirm = QMessageBox.question(
            self,
            "Eliminar servidor",
            f"¿Eliminar '{label}'?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_server(server_id)
        except OSError as error:
            QMessageBox.critical(self, "Error", f"No se pudo eliminar el servidor:\n{error}")
            return
        self._refresh_cards()

    def _connect_server(self, server_id: str) -> None:
        info = load_servers().get(server_id)
        if info is None:
            self._refresh_cards()
            return
        ok, message = open_ssh(info)
        if not ok:
            QMessageBox.critical(self, "Error de conexión", message)
            return
        self.statusBar().showMessage(f"Abriendo consola SSH a {_format_target(info)}...", 5000)

    def _apply_dark_mode(self, enabled: bool) -> None:
        self.dark_mode = enabled
        self.setStyleSheet(DARK_STYLE if enabled else "")

    def toggle_dark_mode(self) -> None:
        self._apply_dark_mode(not self.dark_mode)

    def _center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

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
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tree.write(CONFIG_FILE, encoding="utf-8", xml_declaration=True)

    def closeEvent(self, event) -> None:
        self._save_preferences()
        event.accept()

    def show_server_dialog(self) -> None:
        dialog = ServerDialog(self, dark_mode=self.dark_mode)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_cards()

    def show_instructions(self) -> None:
        HelpDialog(self, dark_mode=self.dark_mode).exec()

    def show_about(self) -> None:
        AboutDialog(self, dark_mode=self.dark_mode).exec()


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(_logo_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
