import queue
import sys
import threading
import time
import uuid
from typing import Any, Callable, Pattern

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

class SettingsUI:
    def __init__(
        self,
        settings_store: Any,
        shared_state: Any,
        debug_log_store: Any,
        reconnect_event: threading.Event,
        manual_refresh_event: threading.Event,
        stop_event: threading.Event,
        *,
        pair_code_re: Pattern[str],
        is_jwt_token_fn: Callable[[str], bool],
        default_device_name_fn: Callable[[], str],
        is_autostart_enabled_windows_fn: Callable[[], bool],
        validate_server_url_fn: Callable[[str], tuple[str, str | None]],
        pair_agent_device_fn: Callable[[str, str, str, str], tuple[dict | None, str | None]],
        apply_agent_auth_payload_fn: Callable[[Any, dict], None],
        update_agent_device_name_fn: Callable[[str, str, str], str | None],
        set_autostart_windows_fn: Callable[[bool], tuple[bool, str]],
        debug_log_fn: Callable[[str, str], None],
    ) -> None:
        self.settings_store = settings_store
        self.shared_state = shared_state
        self.debug_log_store = debug_log_store
        self.reconnect_event = reconnect_event
        self.manual_refresh_event = manual_refresh_event
        self.stop_event = stop_event
        self._pair_code_re = pair_code_re
        self._is_jwt_token = is_jwt_token_fn
        self._default_device_name = default_device_name_fn
        self._is_autostart_enabled_windows = is_autostart_enabled_windows_fn
        self._validate_server_url = validate_server_url_fn
        self._pair_agent_device = pair_agent_device_fn
        self._apply_agent_auth_payload = apply_agent_auth_payload_fn
        self._update_agent_device_name = update_agent_device_name_fn
        self._set_autostart_windows = set_autostart_windows_fn
        self._debug_log = debug_log_fn
        self.ui_queue: "queue.Queue[str]" = queue.Queue()

        self.app = QApplication.instance() or QApplication(sys.argv)
        QApplication.setQuitOnLastWindowClosed(False)

        self.window = QMainWindow()
        self.window.setWindowTitle("GameTracker Agent")
        self.window.resize(1180, 820)
        self.window.setMinimumSize(1080, 760)
        self.window.setAttribute(Qt.WA_StyledBackground, True)

        self.log_cursor = 0
        self.log_autoscroll = True

        self._build_layout()
        self._apply_styles()
        self._setup_tray()

        saved_token = self.settings_store.get_token()
        self.token_entry.setText("" if self._is_jwt_token(saved_token) else saved_token)
        self.server_entry.setText(self.settings_store.get_server_url())
        self.device_id_entry.setText(self.settings_store.get_device_id() or f"gt-{uuid.uuid4().hex[:20]}")
        self.device_id_entry.setReadOnly(self._is_jwt_token(saved_token))
        self.device_name_entry.setText(self.settings_store.get_device_name() or self._default_device_name())
        self.autostart_checkbox.setChecked(self._is_autostart_enabled_windows())
        self.window.hide()

        self.timer = QTimer(self.window)
        self.timer.timeout.connect(self._poll)
        self.timer.start(1000)

    def _apply_styles(self) -> None:
        self.app.setStyleSheet(
            """
            QWidget {
                color: #e8f4ff;
                font-family: "Exo 2", "Segoe UI", "Arial", sans-serif;
                font-size: 13px;
                background: transparent;
            }
            QMainWindow {
                background: qradialgradient(cx:0.12, cy:0.14, radius:0.55, fx:0.12, fy:0.14, stop:0 rgba(21, 174, 255, 0.14), stop:1 rgba(21, 174, 255, 0));
            }
            QWidget#root {
                background:
                    qradialgradient(cx:0.12, cy:0.14, radius:0.55, fx:0.12, fy:0.14, stop:0 rgba(21, 174, 255, 0.14), stop:1 rgba(21, 174, 255, 0)),
                    qradialgradient(cx:0.82, cy:0.06, radius:0.52, fx:0.82, fy:0.06, stop:0 rgba(111, 255, 140, 0.1), stop:1 rgba(111, 255, 140, 0)),
                    qradialgradient(cx:0.46, cy:0.8, radius:0.68, fx:0.46, fy:0.8, stop:0 rgba(38, 83, 164, 0.2), stop:1 rgba(38, 83, 164, 0)),
                    qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #080a11, stop:1 #05070f);
            }
            QLabel, QCheckBox, QTabBar {
                background: transparent;
            }
            QFrame#card {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(19, 28, 49, 0.88), stop:1 rgba(15, 21, 37, 0.92));
                border: 1px solid rgba(154, 173, 210, 0.22);
                border-radius: 16px;
            }
            QLabel#title {
                color: #f4f9ff;
                font-size: 20px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }
            QLabel#subtitle {
                color: #97abcc;
                font-size: 12px;
            }
            QTabWidget#mainTabs::pane {
                border: 1px solid rgba(154, 173, 210, 0.22);
                border-radius: 12px;
                top: -2px;
                background: rgba(16, 23, 40, 0.82);
            }
            QTabWidget#mainTabs QTabBar::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(22, 31, 54, 0.92), stop:1 rgba(14, 22, 38, 0.92));
                border: 1px solid rgba(154, 173, 210, 0.22);
                border-bottom: none;
                color: #97abcc;
                padding: 10px 16px;
                margin-right: 4px;
                margin-bottom: -2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-weight: 600;
            }
            QTabWidget#mainTabs QTabBar::tab:selected {
                color: #f4f9ff;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(14, 184, 229, 0.32), stop:1 rgba(11, 84, 171, 0.35));
                border-color: rgba(20, 212, 255, 0.58);
            }
            QTabWidget#mainTabs QTabBar::tab:hover:!selected {
                border-color: rgba(20, 212, 255, 0.42);
                color: #e8f4ff;
            }
            QTabWidget#mainTabs > QWidget {
                background: rgba(12, 18, 32, 0.54);
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QLabel#sectionTitle {
                color: rgba(171, 197, 232, 0.88);
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.9px;
                text-transform: uppercase;
            }
            QLineEdit, QTextEdit {
                background: rgba(5, 10, 20, 0.62);
                border: 1px solid rgba(120, 141, 180, 0.4);
                border-radius: 11px;
                padding: 9px 11px;
                selection-background-color: rgba(20, 212, 255, 0.32);
            }
            QLineEdit {
                min-height: 36px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid rgba(20, 212, 255, 0.8);
                background: rgba(8, 15, 29, 0.78);
            }
            QTextEdit#codePanel {
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 12px;
                line-height: 1.35;
                background: rgba(8, 15, 29, 0.68);
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(22, 31, 54, 0.92), stop:1 rgba(14, 22, 38, 0.92));
                border: 1px solid rgba(154, 173, 210, 0.22);
                border-radius: 12px;
                padding: 9px 16px;
                color: #e8f4ff;
                font-weight: 600;
                min-height: 24px;
            }
            QPushButton:hover {
                border: 1px solid rgba(20, 212, 255, 0.42);
            }
            QPushButton:pressed {
                background: rgba(11, 23, 40, 0.96);
                border: 1px solid rgba(120, 141, 180, 0.55);
            }
            QPushButton#primaryButton {
                border: 1px solid rgba(20, 212, 255, 0.58);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(14, 184, 229, 0.32), stop:1 rgba(11, 84, 171, 0.35));
            }
            QPushButton#primaryButton:hover {
                border: 1px solid rgba(20, 212, 255, 0.8);
            }
            QPushButton#ghostButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(15, 23, 40, 0.88), stop:1 rgba(10, 16, 29, 0.9));
                border: 1px solid rgba(120, 141, 180, 0.42);
                color: #c6d8f4;
            }
            QPushButton#ghostButton:hover {
                border: 1px solid rgba(20, 212, 255, 0.42);
                color: #e8f4ff;
            }
            QPushButton:disabled {
                color: rgba(200, 214, 236, 0.45);
                border: 1px solid rgba(120, 141, 180, 0.2);
                background: rgba(20, 35, 58, 0.45);
            }
            QCheckBox {
                color: #a9bddf;
                spacing: 7px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 5px;
                border: 1px solid rgba(133, 171, 226, 0.78);
                background: rgba(16, 32, 58, 0.82);
            }
            QCheckBox::indicator:hover {
                border-color: rgba(20, 212, 255, 0.86);
                background: rgba(20, 48, 86, 0.9);
            }
            QCheckBox::indicator:checked {
                background: #14d4ff;
                border-color: #63d3ff;
            }
            QCheckBox::indicator:checked:disabled,
            QCheckBox::indicator:disabled {
                background: rgba(19, 36, 61, 0.84);
                border-color: rgba(133, 171, 226, 0.45);
            }
            QLabel#statusLine {
                color: #baffd0;
                padding: 7px 10px;
                background: rgba(111, 255, 140, 0.08);
                border: 1px solid rgba(111, 255, 140, 0.26);
                border-radius: 8px;
            }
            QMenu {
                background: #101728;
                border: 1px solid rgba(154, 173, 210, 0.22);
                border-radius: 8px;
            }
            QMenu::item {
                padding: 7px 18px;
            }
            QMenu::item:selected {
                background: rgba(20, 212, 255, 0.22);
            }
            """
        )

    def _build_layout(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        title_card = QFrame()
        title_card.setObjectName("card")
        title_card.setAttribute(Qt.WA_StyledBackground, True)
        title_layout = QVBoxLayout(title_card)
        title_layout.setContentsMargins(14, 12, 14, 12)
        title_layout.setSpacing(3)

        title_label = QLabel("GameTracker Agent")
        title_label.setObjectName("title")
        title_layout.addWidget(title_label)

        subtitle_label = QLabel("Desktop bridge for pairing, sync and launch telemetry")
        subtitle_label.setObjectName("subtitle")
        title_layout.addWidget(subtitle_label)
        root_layout.addWidget(title_card)

        tabs = QTabWidget()
        tabs.setObjectName("mainTabs")
        tabs.setDocumentMode(True)
        root_layout.addWidget(tabs)

        settings_tab = QWidget()
        logs_tab = QWidget()
        tabs.addTab(settings_tab, "Настройки")
        tabs.addTab(logs_tab, "Логи")

        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(14, 14, 14, 14)
        settings_layout.setSpacing(12)

        connect_card = QFrame()
        connect_card.setObjectName("card")
        connect_card.setAttribute(Qt.WA_StyledBackground, True)
        connect_layout = QVBoxLayout(connect_card)
        connect_layout.setContentsMargins(14, 14, 14, 14)
        connect_layout.setSpacing(10)

        credentials_title = QLabel("CONNECTION")
        credentials_title.setObjectName("sectionTitle")
        connect_layout.addWidget(credentials_title)

        token_label = QLabel("Pair Code (6 digits)")
        token_label.setObjectName("sectionTitle")
        connect_layout.addWidget(token_label)

        token_row = QHBoxLayout()
        token_row.setSpacing(8)
        connect_layout.addLayout(token_row)

        self.token_entry = QLineEdit()
        self.token_entry.setEchoMode(QLineEdit.Password)
        token_row.addWidget(self.token_entry, 1)
        self._attach_context_menu(self.token_entry, read_only=False)

        self.show_token_checkbox = QCheckBox("Show")
        self.show_token_checkbox.toggled.connect(self._toggle_show_token)
        token_row.addWidget(self.show_token_checkbox, 0, Qt.AlignVCenter)

        server_label = QLabel("Server URL")
        server_label.setObjectName("sectionTitle")
        connect_layout.addWidget(server_label)

        self.server_entry = QLineEdit()
        connect_layout.addWidget(self.server_entry)
        self._attach_context_menu(self.server_entry, read_only=False)

        device_grid = QGridLayout()
        device_grid.setHorizontalSpacing(10)
        device_grid.setVerticalSpacing(6)
        connect_layout.addLayout(device_grid)
        device_id_label = QLabel("Device ID")
        device_id_label.setObjectName("sectionTitle")
        device_grid.addWidget(device_id_label, 0, 0)
        device_name_label = QLabel("Device Name")
        device_name_label.setObjectName("sectionTitle")
        device_grid.addWidget(device_name_label, 0, 1)
        self.device_id_entry = QLineEdit()
        self.device_id_entry.setMinimumWidth(280)
        device_grid.addWidget(self.device_id_entry, 1, 0)
        self._attach_context_menu(self.device_id_entry, read_only=False)
        self.device_name_entry = QLineEdit()
        device_grid.addWidget(self.device_name_entry, 1, 1)
        device_grid.setColumnStretch(0, 1)
        device_grid.setColumnStretch(1, 2)
        self._attach_context_menu(self.device_name_entry, read_only=False)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        connect_layout.addLayout(buttons_row)

        save_btn = QPushButton("Save/Pair")
        save_btn.setObjectName("primaryButton")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_token)
        buttons_row.addWidget(save_btn)

        reconnect_btn = QPushButton("Reconnect")
        reconnect_btn.setObjectName("ghostButton")
        reconnect_btn.setCursor(Qt.PointingHandCursor)
        reconnect_btn.clicked.connect(self._reconnect)
        buttons_row.addWidget(reconnect_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("ghostButton")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_now)
        buttons_row.addWidget(refresh_btn)

        re_pair_btn = QPushButton("Re-pair as new device")
        re_pair_btn.setObjectName("ghostButton")
        re_pair_btn.setCursor(Qt.PointingHandCursor)
        re_pair_btn.clicked.connect(self._re_pair_device)
        buttons_row.addWidget(re_pair_btn)
        buttons_row.addStretch(1)

        self.autostart_checkbox = QCheckBox("Enable autostart on login")
        self.autostart_checkbox.setCursor(Qt.PointingHandCursor)
        self.autostart_checkbox.toggled.connect(self._toggle_autostart)
        connect_layout.addWidget(self.autostart_checkbox)
        settings_layout.addWidget(connect_card)

        games_card = QFrame()
        games_card.setObjectName("card")
        games_card.setAttribute(Qt.WA_StyledBackground, True)
        games_layout = QVBoxLayout(games_card)
        games_layout.setContentsMargins(14, 14, 14, 14)
        games_layout.setSpacing(8)

        games_label = QLabel("Tracked games")
        games_label.setObjectName("sectionTitle")
        games_layout.addWidget(games_label)

        self.games_box = QTextEdit()
        self.games_box.setObjectName("codePanel")
        self.games_box.setReadOnly(True)
        games_layout.addWidget(self.games_box, 1)
        self._attach_context_menu(self.games_box, read_only=True)

        self.status_label = QLabel("Disconnected")
        self.status_label.setObjectName("statusLine")
        self.status_label.setWordWrap(True)
        games_layout.addWidget(self.status_label)
        settings_layout.addWidget(games_card, 1)

        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(14, 14, 14, 14)
        logs_layout.setSpacing(12)

        logs_card = QFrame()
        logs_card.setObjectName("card")
        logs_card.setAttribute(Qt.WA_StyledBackground, True)
        logs_card_layout = QVBoxLayout(logs_card)
        logs_card_layout.setContentsMargins(14, 14, 14, 14)
        logs_card_layout.setSpacing(10)

        logs_header = QLabel("RUNTIME LOGS")
        logs_header.setObjectName("sectionTitle")
        logs_card_layout.addWidget(logs_header)

        logs_tools_row = QHBoxLayout()
        logs_card_layout.addLayout(logs_tools_row)

        clear_btn = QPushButton("Очистить")
        clear_btn.setObjectName("ghostButton")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_logs)
        logs_tools_row.addWidget(clear_btn)

        self.logs_autoscroll_checkbox = QCheckBox("Автопрокрутка")
        self.logs_autoscroll_checkbox.setCursor(Qt.PointingHandCursor)
        self.logs_autoscroll_checkbox.setChecked(True)
        self.logs_autoscroll_checkbox.toggled.connect(self._set_log_autoscroll)
        logs_tools_row.addWidget(self.logs_autoscroll_checkbox)
        logs_tools_row.addStretch(1)

        self.logs_box = QTextEdit()
        self.logs_box.setObjectName("codePanel")
        self.logs_box.setReadOnly(True)
        logs_card_layout.addWidget(self.logs_box, 1)
        self._attach_context_menu(self.logs_box, read_only=True)
        logs_layout.addWidget(logs_card, 1)

        self.window.setCentralWidget(central)
        self.window.closeEvent = self._on_close_event

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._debug_log("TRAY", "System tray is unavailable; tray icon disabled")
            self.tray_icon = None
            return

        tray_icon = self._create_icon()
        if tray_icon.isNull():
            tray_icon = self.window.style().standardIcon(QStyle.SP_ComputerIcon)

        self.tray_icon = QSystemTrayIcon(tray_icon, self.window)
        self.tray_icon.setToolTip("GameTracker Agent")

        menu = QMenu(self.window)
        open_action = QAction("Настройки", self.window)
        open_action.triggered.connect(self.request_show)
        menu.addAction(open_action)

        exit_action = QAction("Выход", self.window)
        exit_action.triggered.connect(self._exit_from_tray)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        self._debug_log("TRAY", "Tray icon started")

    def _create_icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#10b981"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
        painter.setBrush(QColor("#059669"))
        painter.drawRoundedRect(10, 20, 44, 24, 8, 8)
        painter.setBrush(QColor("#34d399"))
        painter.drawRect(18, 28, 8, 8)
        painter.drawRect(38, 28, 8, 8)
        pen = QPen(QColor("#8fffe2"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
        painter.end()
        return QIcon(pix)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.request_show()

    def _on_close_event(self, event) -> None:
        self.hide()
        event.ignore()

    def _toggle_show_token(self, checked: bool) -> None:
        self.token_entry.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _set_log_autoscroll(self, checked: bool) -> None:
        self.log_autoscroll = bool(checked)

    def _attach_context_menu(self, widget: QWidget, read_only: bool) -> None:
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos, w=widget, ro=read_only: self._show_context_menu(w, pos, ro)
        )

    def _show_context_menu(self, widget: QWidget, pos: QPoint, read_only: bool) -> None:
        menu = QMenu(self.window)
        cut_action = menu.addAction("Вырезать")
        copy_action = menu.addAction("Копировать")
        paste_action = menu.addAction("Вставить")
        menu.addSeparator()
        select_all_action = menu.addAction("Выделить всё")

        if isinstance(widget, QLineEdit):
            cut_action.triggered.connect(widget.cut)
            copy_action.triggered.connect(widget.copy)
            paste_action.triggered.connect(widget.paste)
            select_all_action.triggered.connect(widget.selectAll)
            copy_action.setEnabled(widget.hasSelectedText())
            cut_action.setEnabled(widget.hasSelectedText() and not read_only)
            paste_action.setEnabled(not read_only)
            global_pos = widget.mapToGlobal(pos)
        elif isinstance(widget, QTextEdit):
            cut_action.triggered.connect(widget.cut)
            copy_action.triggered.connect(widget.copy)
            paste_action.triggered.connect(widget.paste)
            select_all_action.triggered.connect(widget.selectAll)
            copy_action.setEnabled(widget.textCursor().hasSelection())
            cut_action.setEnabled(widget.textCursor().hasSelection() and not read_only)
            paste_action.setEnabled(not read_only)
            global_pos = widget.mapToGlobal(pos)
        else:
            return

        menu.exec(global_pos)

    def _save_token(self, _checked: bool = False) -> None:
        token = self.token_entry.text().strip()
        server_url = self.server_entry.text().strip()
        valid_server_url, server_url_error = self._validate_server_url(server_url)
        if server_url_error:
            self._debug_log("UI", f"Save/Pair rejected: invalid server URL ({server_url_error})")
            QMessageBox.critical(self.window, "Server URL", f"Invalid server URL: {server_url_error}")
            return
        device_id = self.device_id_entry.text().strip()
        if not device_id:
            device_id = f"gt-{uuid.uuid4().hex[:20]}"
            self.device_id_entry.setText(device_id)
        device_name = self.device_name_entry.text().strip() or self._default_device_name()
        stored_token = self.settings_store.get_token().strip()
        is_paired = self._is_jwt_token(stored_token)
        stored_device_id = self.settings_store.get_device_id().strip()

        if is_paired and stored_device_id and device_id != stored_device_id:
            device_id = stored_device_id
            self.device_id_entry.setText(device_id)
            QMessageBox.information(
                self.window,
                "Device ID",
                "Device ID is fixed after pairing. Re-pair the agent to use a new Device ID.",
            )

        if token and self._pair_code_re.fullmatch(token):
            self._debug_log("UI", f"Pair requested for device_id={device_id}")
            payload, err = self._pair_agent_device(valid_server_url, token, device_id, device_name)
            if err:
                self._debug_log("UI", f"Pair failed: {err}")
                QMessageBox.critical(self.window, "Pairing", f"Pair failed: {err}")
                return
            self._apply_agent_auth_payload(self.settings_store, payload or {})
            self.token_entry.setText("")
            self.server_entry.setText(valid_server_url)
            self.device_id_entry.setText(self.settings_store.get_device_id())
            self.device_id_entry.setReadOnly(True)
            self.device_name_entry.setText(self.settings_store.get_device_name() or device_name)
            self.reconnect_event.set()
            self._debug_log("UI", "Pair success; reconnect requested")
            QMessageBox.information(self.window, "Pairing", "Device paired successfully.")
            return

        if token:
            self._debug_log("UI", "Save/Pair rejected: non-empty token is not a 6-digit pair code")
            QMessageBox.critical(self.window, "Pairing", "Enter 6-digit pair code from web settings.")
            return
        self.settings_store.set_server_url(valid_server_url)
        self.settings_store.set_device_id(device_id)
        self.settings_store.set_device_name(device_name)
        self.settings_store.save()

        if is_paired:
            update_err = self._update_agent_device_name(valid_server_url, stored_token, device_name)
            if update_err:
                QMessageBox.warning(
                    self.window,
                    "Device Name",
                    f"Saved locally, but server name update failed:\n{update_err}",
                )

        self.reconnect_event.set()
        self._debug_log("UI", f"Settings saved; reconnect requested for {valid_server_url}")

    def _toggle_autostart(self, _checked: bool = False) -> None:
        desired = bool(self.autostart_checkbox.isChecked())
        ok, err = self._set_autostart_windows(desired)
        if not ok:
            self.autostart_checkbox.blockSignals(True)
            self.autostart_checkbox.setChecked(not desired)
            self.autostart_checkbox.blockSignals(False)
            self._debug_log("UI", f"Autostart change failed: {err}")
            QMessageBox.critical(self.window, "Autostart", err)
            return
        self.settings_store.set_autostart(desired)
        self.settings_store.save()
        self._debug_log("UI", f"Autostart set to {desired}")

    def _refresh_now(self, _checked: bool = False) -> None:
        self.manual_refresh_event.set()
        self._debug_log("UI", "Refresh requested (manual config+commands refresh)")

    def _reconnect(self, _checked: bool = False) -> None:
        self.reconnect_event.set()
        self._debug_log("UI", "Reconnect requested")

    def _render_games(self) -> None:
        items = self.shared_state.get_config_items()
        lines = []
        for item in items:
            enabled = "ON" if item.get("enabled", True) else "OFF"
            lines.append(
                f"[{enabled}] {item.get('title') or 'Untitled'} | {item.get('exe_name') or '-'} | "
                f"{item.get('launch_path') or '-'}"
            )
        self.games_box.setPlainText("\n".join(lines) if lines else "No synced games")

    def _render_logs(self) -> None:
        next_cursor, lines = self.debug_log_store.read_since(self.log_cursor)
        self.log_cursor = next_cursor
        if not lines:
            return
        self.logs_box.append("\n".join(lines))
        if self.log_autoscroll:
            self.logs_box.moveCursor(QTextCursor.End)

    def _clear_logs(self, _checked: bool = False) -> None:
        self.logs_box.clear()
        self.log_cursor = self.debug_log_store.clear()
        self._debug_log("UI", "Logs cleared from GUI")

    def _format_age(self, ts: float) -> str:
        if not ts:
            return "never"
        delta = max(0, int(time.time() - ts))
        if delta < 60:
            return f"{delta}s ago"
        if delta < 3600:
            return f"{delta // 60}m ago"
        return f"{delta // 3600}h ago"

    def _re_pair_device(self, _checked: bool = False) -> None:
        answer = QMessageBox.question(
            self.window,
            "Re-pair device",
            "This will clear current agent tokens and generate a new Device ID.\n"
            "Use pair code from web settings to pair again.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        new_device_id = f"gt-{uuid.uuid4().hex[:20]}"
        self.settings_store.set_token("")
        self.settings_store.set_refresh_token("")
        self.settings_store.set_access_expires_at(0)
        self.settings_store.set_device_id(new_device_id)
        self.settings_store.save()

        self.token_entry.setText("")
        self.device_id_entry.setReadOnly(False)
        self.device_id_entry.setText(new_device_id)
        self.reconnect_event.set()
        self._debug_log("UI", "Re-pair mode enabled: tokens cleared and new device_id generated")
        QMessageBox.information(self.window, "Re-pair", "Agent reset. Enter pair code and click Save/Pair.")

    def _poll(self) -> None:
        if self.stop_event.is_set():
            if self.tray_icon is not None:
                self.tray_icon.hide()
            self.app.quit()
            return

        while True:
            try:
                cmd = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if cmd == "show":
                self.show()

        ws_text = "Connected via WebSocket" if self.shared_state.is_ws_connected() else "Disconnected"
        err = self.shared_state.get_last_error()
        health = self.shared_state.get_health_snapshot()
        api_text = "API OK" if health["api_ok"] else "API unavailable"
        status_lines = [
            f"{ws_text} | {api_text}",
            (
                f"Config: {self._format_age(health['last_config_sync_at'])} | "
                f"Commands polled: {self._format_age(health['last_command_poll_at'])} | "
                f"Commands executed: {self._format_age(health['last_command_exec_at'])}"
            ),
            f"Ping: {self._format_age(health['last_ping_at'])} (last cycle sent {int(health['last_ping_count'])})",
        ]
        if err:
            status_lines.append(f"Error: {err}")
        self.status_label.setText("\n".join(status_lines))
        self._render_games()
        self._render_logs()

    def show(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        self._debug_log("UI", "Window shown")

    def hide(self) -> None:
        self.window.hide()
        self._debug_log("UI", "Window hidden")

    def request_show(self, _checked: bool = False) -> None:
        self.ui_queue.put("show")
        self._debug_log("UI", "Show requested from tray")

    def _exit_from_tray(self, _checked: bool = False) -> None:
        self.stop_event.set()
        self._debug_log("TRAY", "Exit clicked")
        self.app.quit()

    def run(self) -> int:
        return self.app.exec()
