import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import main
from main import AboutDialog, HelpDialog, MainWindow, ServerCard, ServerDialog


def _menu_titles(window):
    return [action.text() for action in window.menuBar().actions()]


def _action_texts(window, menu_index):
    menu = window.menuBar().actions()[menu_index].menu()
    return [action.text() for action in menu.actions()]


def test_menus(qapp):
    window = MainWindow()
    assert _menu_titles(window) == ["Archivo", "Ver", "Ayuda"]


def test_file_menu_actions(qapp):
    window = MainWindow()
    actions = _action_texts(window, 0)
    assert "Nuevo servidor..." in actions
    assert "Importar servidores..." in actions
    assert "Exportar servidores..." in actions
    assert "Salir" in actions


def test_view_menu_has_dark_mode_toggle(qapp):
    window = MainWindow()
    assert "Alternar modo oscuro/claro" in _action_texts(window, 1)


def test_help_menu_actions(qapp):
    window = MainWindow()
    assert _action_texts(window, 2) == ["Instrucciones", "Acerca de..."]


def test_toggle_dark_mode(qapp):
    window = MainWindow()
    assert window.dark_mode is False
    window.toggle_dark_mode()
    assert window.dark_mode is True
    assert window.styleSheet() != ""
    window.toggle_dark_mode()
    assert window.dark_mode is False
    assert window.styleSheet() == ""


def test_dialogs_construct(qapp):
    assert AboutDialog(dark_mode=True).windowTitle() == "Acerca de"
    assert HelpDialog().windowTitle() == "Instrucciones"
    assert ServerDialog().windowTitle() == "Nuevo servidor"
    assert ServerDialog(server_id="prod", info={}).windowTitle() == "Editar servidor"


def test_about_dialog_credits_and_version(qapp):
    from PyQt6.QtWidgets import QLabel

    assert main.PROGRAM_VERSION == "0.5.0"
    dialog = AboutDialog()
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "v0.5.0" in labels
    assert "Programado por @EdFasano70" in labels


def test_preferences_persisted(qapp):
    window = MainWindow()
    window.resize(333, 444)
    window.move(11, 22)
    window.toggle_dark_mode()
    window._save_preferences()

    root = ET.parse(main.CONFIG_FILE).getroot()
    assert root.findtext("window/width") == "333"
    assert root.findtext("window/height") == "444"
    assert root.findtext("window/x") == "11"
    assert root.findtext("window/y") == "22"
    assert root.findtext("settings/dark_mode") == "true"

    restored = MainWindow()
    assert restored.width() == 333
    assert restored.height() == 444
    assert restored.dark_mode is True
    assert restored.styleSheet() != ""


def test_servers_persisted(qapp):
    main.save_servers(
        {
            "prod": {
                "label": "Producción",
                "username": "root",
                "password": "secreto",
                "host": "10.0.0.5",
                "port": "22",
            }
        }
    )
    servers = main.load_servers()
    assert servers["prod"]["label"] == "Producción"
    assert servers["prod"]["password"] == "secreto"

    # La contraseña se guarda codificada en disco, no en claro.
    raw = main.SERVERS_FILE.read_text(encoding="utf-8")
    assert "secreto" not in raw


def test_create_server_roundtrip(qapp):
    main.save_servers({})
    server_id = main.create_server("Produccion", "root", "clave", "10.0.0.5", "22")
    assert server_id == "produccion"

    servers = main.load_servers()
    assert servers["produccion"]["username"] == "root"
    assert servers["produccion"]["password"] == "clave"
    assert servers["produccion"]["host"] == "10.0.0.5"
    assert servers["produccion"]["port"] == "22"


def test_create_server_validates(qapp):
    main.save_servers({})
    with pytest.raises(ValueError):
        main.create_server("", "root", "", "10.0.0.5", "22")
    with pytest.raises(ValueError):
        main.create_server("X", "", "", "10.0.0.5", "22")
    with pytest.raises(ValueError):
        main.create_server("X", "root", "", "", "22")
    with pytest.raises(ValueError):
        main.create_server("X", "root", "", "10.0.0.5", "no-es-puerto")
    with pytest.raises(ValueError):
        main.create_server("X", "root", "", "10.0.0.5", "70000")


def test_create_server_overwrite_guard(qapp):
    main.save_servers({})
    main.create_server("Produccion", "root", "", "10.0.0.5", "22")
    with pytest.raises(FileExistsError):
        main.create_server("Produccion", "root", "", "10.0.0.6", "22")


def test_delete_server(qapp):
    main.save_servers({})
    main.create_server("Produccion", "root", "", "10.0.0.5", "22")
    main.delete_server("produccion")
    assert main.load_servers() == {}


def test_ssh_shell():
    shell = main._ssh_shell({"username": "root", "host": "10.0.0.5"})
    assert shell == "ssh -o StrictHostKeyChecking=accept-new root@10.0.0.5"

    shell = main._ssh_shell({"username": "root", "host": "10.0.0.5", "port": "2222"})
    assert shell == "ssh -o StrictHostKeyChecking=accept-new -p 2222 root@10.0.0.5"

    shell = main._ssh_shell({"host": "host"})
    assert shell == "ssh -o StrictHostKeyChecking=accept-new host"

    # con sshpass (si está disponible)
    if shutil.which("sshpass"):
        shell = main._ssh_shell({"username": "root", "host": "10.0.0.5", "password": "clave"})
        assert shell.startswith("sshpass -p ")
        assert shell.endswith("ssh -o StrictHostKeyChecking=accept-new root@10.0.0.5")


def test_cards_render_for_servers(qapp):
    main.save_servers(
        {"a": {"label": "A", "username": "u", "password": "", "host": "h", "port": "22"}}
    )
    window = MainWindow()
    assert len(window.cards_container.findChildren(ServerCard)) == 1


def test_empty_state(qapp):
    main.save_servers({})
    window = MainWindow()
    assert window.cards_container.findChildren(ServerCard) == []


def test_menu_actions_have_icons(qapp):
    window = MainWindow()
    for menu_index in range(3):
        for action in window.menuBar().actions()[menu_index].menu().actions():
            if not action.isSeparator():
                assert not action.icon().isNull(), action.text()


def test_logo_used_as_app_icon(qapp):
    assert main.LOGO_FILE.is_file()
    assert not MainWindow().windowIcon().isNull()
    assert not AboutDialog().windowIcon().isNull()


def test_import_servers(qapp):
    main.save_servers({})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as tmp:
        tmp.write(
            """<servers>
  <server>
    <label>Test Server</label>
    <username>admin</username>
    <password>password</password>
    <host>10.0.0.1</host>
    <port>22</port>
  </server>
</servers>"""
        )
        temp_path = tmp.name
    try:
        count = main.import_servers(temp_path)
        servers = main.load_servers()
        assert count == 1
        assert len(servers) == 1
        assert "test-server" in servers
        assert servers["test-server"]["username"] == "admin"
        assert servers["test-server"]["password"] == "password"
        assert servers["test-server"]["host"] == "10.0.0.1"
        assert servers["test-server"]["port"] == "22"
    finally:
        os.unlink(temp_path)


def test_import_servers_skips_invalid(qapp):
    main.save_servers({})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as tmp:
        tmp.write(
            """<servers>
  <server>
    <label>Valido</label>
    <username>root</username>
    <host>10.0.0.1</host>
    <port>22</port>
  </server>
  <server>
    <label></label>
    <username>root</username>
    <host>10.0.0.2</host>
    <port>22</port>
  </server>
</servers>"""
        )
        temp_path = tmp.name
    try:
        count = main.import_servers(temp_path)
        assert count == 1
        assert set(main.load_servers()) == {"valido"}
    finally:
        os.unlink(temp_path)


def test_export_servers(qapp):
    main.save_servers(
        {
            "test": {
                "label": "Test",
                "username": "admin",
                "password": "secret",
                "host": "10.0.0.1",
                "port": "22",
            }
        }
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        count = main.export_servers(tmp_path)
        assert count == 1
        content = Path(tmp_path).read_text(encoding="utf-8")
        assert "<servers>" in content
        assert "<server>" in content
        assert "<label>Test</label>" in content
        assert "<username>admin</username>" in content
        assert "<password>secret</password>" in content
        assert "<host>10.0.0.1</host>" in content
        assert "<port>22</port>" in content
    finally:
        os.unlink(tmp_path)


def test_import_export_roundtrip(qapp):
    main.save_servers({})
    main.create_server("TestServer", "admin", "secret", "10.0.0.1", "22")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        assert main.export_servers(tmp_path) == 1
        main.save_servers({})
        assert main.import_servers(tmp_path) == 1

        servers = main.load_servers()
        assert set(servers) == {"testserver"}
        assert servers["testserver"]["username"] == "admin"
        assert servers["testserver"]["password"] == "secret"
        assert servers["testserver"]["host"] == "10.0.0.1"
        assert servers["testserver"]["port"] == "22"
    finally:
        os.unlink(tmp_path)
