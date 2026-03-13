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
    QSizePolicy,
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
        apply_agent_pairing_payload_fn: Callable[[Any, str, dict], None],
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
        self._apply_agent_pairing_payload = apply_agent_pairing_payload_fn
        self._update_agent_device_name = update_agent_device_name_fn
        self._set_autostart_windows = set_autostart_windows_fn
        self._debug_log = debug_log_fn
        self.ui_queue: "queue.Queue[str]" = queue.Queue()

        self.app = QApplication.instance() or QApplication(sys.argv)
        QApplication.setQuitOnLastWindowClosed(False)

        self.window = QMainWindow()
        self.window.setWindowTitle("GameTracker Agent")
        self.window.resize(1100, 700)
        self.window.setMinimumSize(980, 660)
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
                color: #eaf2ff;
                font-family: "Exo 2", "Segoe UI", "Arial", sans-serif;
                font-size: 12px;
                background: transparent;
            }
            QMainWindow {
                background: #081223;
            }
            QWidget#root {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0a1830, stop:1 #081223);
            }
            QLabel, QCheckBox, QTabBar {
                background: transparent;
            }
            QFrame#shellCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(14, 26, 49, 0.96), stop:1 rgba(10, 20, 41, 0.96));
                border: 1px solid rgba(114, 145, 196, 0.36);
                border-radius: 12px;
            }
            QWidget#shellHeader {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(15, 31, 58, 0.96), stop:1 rgba(11, 23, 45, 0.96));
                border-bottom: 1px solid rgba(114, 145, 196, 0.3);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#card {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(14, 27, 52, 0.84), stop:1 rgba(11, 22, 43, 0.86));
                border: 1px solid rgba(126, 160, 216, 0.32);
                border-radius: 10px;
            }
            QFrame#connectCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(14, 27, 52, 0.84), stop:1 rgba(11, 22, 43, 0.86));
                border: 1px solid rgba(126, 160, 216, 0.32);
                border-radius: 10px;
                border-top-left-radius: 0px;
            }
            QLabel#title {
                color: #f6faff;
                font-size: 18px;
                font-weight: 700;
                letter-spacing: 0.2px;
            }
            QLabel#subtitle {
                color: #9ab0d2;
                font-size: 11px;
            }
            QTabWidget#mainTabs {
                background: transparent;
            }
            QTabWidget#mainTabs::pane {
                border-top: 1px solid rgba(114, 145, 196, 0.32);
                background: transparent;
                top: 0px;
            }
            QTabWidget#mainTabs QTabBar::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(17, 33, 60, 0.98), stop:1 rgba(13, 24, 46, 0.98));
                border: 1px solid rgba(126, 160, 216, 0.36);
                border-bottom: none;
                color: #9fb5d8;
                padding: 7px 12px;
                margin-right: 4px;
                margin-bottom: 0px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 600;
            }
            QTabWidget#mainTabs QTabBar::tab:selected {
                color: #f5fbff;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(41, 137, 255, 0.48), stop:1 rgba(23, 101, 214, 0.46));
                border-color: rgba(88, 188, 255, 0.74);
            }
            QTabWidget#mainTabs QTabBar::tab:hover:!selected {
                border-color: rgba(57, 174, 255, 0.5);
                color: #eaf2ff;
            }
            QTabWidget#mainTabs > QWidget {
                background: transparent;
            }
            QLabel#sectionTitle {
                color: rgba(167, 197, 236, 0.9);
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.8px;
                margin-top: 4px;
                margin-bottom: 1px;
            }
            QLineEdit, QTextEdit {
                background: rgba(7, 14, 28, 0.84);
                border: 1px solid rgba(116, 143, 188, 0.42);
                border-radius: 9px;
                padding: 6px 10px;
                selection-background-color: rgba(57, 174, 255, 0.34);
            }
            QLineEdit {
                min-height: 30px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid rgba(57, 174, 255, 0.9);
                background: rgba(7, 14, 27, 0.84);
            }
            QTextEdit#codePanel {
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 11px;
                background: rgba(7, 14, 28, 0.84);
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(19, 29, 50, 0.94), stop:1 rgba(13, 20, 35, 0.94));
                border: 1px solid rgba(137, 166, 212, 0.28);
                border-radius: 9px;
                padding: 6px 12px;
                color: #eaf2ff;
                font-weight: 600;
                min-height: 20px;
            }
            QPushButton:hover {
                border: 1px solid rgba(57, 174, 255, 0.56);
            }
            QPushButton:pressed {
                background: rgba(9, 18, 33, 0.96);
                border: 1px solid rgba(116, 143, 188, 0.6);
            }
            QPushButton#primaryButton {
                border: 1px solid rgba(57, 174, 255, 0.72);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(43, 156, 255, 0.36), stop:1 rgba(24, 103, 217, 0.36));
            }
            QPushButton#primaryButton:hover {
                border: 1px solid rgba(92, 194, 255, 0.96);
            }
            QPushButton#ghostButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(13, 21, 37, 0.92), stop:1 rgba(9, 15, 28, 0.92));
                border: 1px solid rgba(116, 143, 188, 0.46);
                color: #c8daf6;
            }
            QPushButton#ghostButton:hover {
                border: 1px solid rgba(57, 174, 255, 0.56);
                color: #eaf2ff;
            }
            QPushButton:disabled {
                color: rgba(194, 211, 240, 0.44);
                border: 1px solid rgba(116, 143, 188, 0.22);
                background: rgba(16, 29, 52, 0.46);
            }
            QCheckBox {
                color: #acc0e2;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 4px;
                border: 1px solid rgba(133, 171, 226, 0.8);
                background: rgba(15, 30, 56, 0.84);
            }
            QCheckBox::indicator:hover {
                border-color: rgba(57, 174, 255, 0.9);
                background: rgba(18, 44, 80, 0.92);
            }
            QCheckBox::indicator:checked {
                background: #2da5ff;
                border-color: #7ac8ff;
            }
            QCheckBox::indicator:checked:disabled,
            QCheckBox::indicator:disabled {
                background: rgba(18, 34, 58, 0.84);
                border-color: rgba(133, 171, 226, 0.46);
            }
            QLabel#statusLine {
                color: #bcffd8;
                padding: 6px 8px;
                background: rgba(24, 140, 107, 0.14);
                border: 1px solid rgba(75, 206, 155, 0.34);
                border-radius: 7px;
            }
            QMenu {
                background: #0f1627;
                border: 1px solid rgba(137, 166, 212, 0.24);
                border-radius: 8px;
            }
            QMenu::item {
                padding: 6px 16px;
            }
            QMenu::item:selected {
                background: rgba(57, 174, 255, 0.24);
            }
            """
        )

    def _build_layout(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(0)

        shell_card = QFrame()
        shell_card.setObjectName("shellCard")
        shell_card.setAttribute(Qt.WA_StyledBackground, True)
        shell_layout = QVBoxLayout(shell_card)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        shell_header = QWidget()
        shell_header.setObjectName("shellHeader")
        shell_header.setAttribute(Qt.WA_StyledBackground, True)
        title_layout = QVBoxLayout(shell_header)
        title_layout.setContentsMargins(14, 10, 14, 10)
        title_layout.setSpacing(2)

        title_label = QLabel("GameTracker Agent")
        title_label.setObjectName("title")
        title_layout.addWidget(title_label)

        subtitle_label = QLabel("Desktop bridge for pairing, sync and launch telemetry")
        subtitle_label.setObjectName("subtitle")
        title_layout.addWidget(subtitle_label)
        shell_layout.addWidget(shell_header)

        tabs_container = QWidget()
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(10, 6, 10, 10)
        tabs_layout.setSpacing(6)

        tabs = QTabWidget()
        tabs.setObjectName("mainTabs")
        tabs.setDocumentMode(True)
        tabs_layout.addWidget(tabs, 1)
        shell_layout.addWidget(tabs_container, 1)

        root_layout.addWidget(shell_card, 1)

        settings_tab = QWidget()
        logs_tab = QWidget()
        tabs.addTab(settings_tab, "Настройки")
        tabs.addTab(logs_tab, "Логи")

        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(8)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)
        settings_layout.addLayout(settings_row, 1)

        connect_card = QFrame()
        connect_card.setObjectName("connectCard")
        connect_card.setAttribute(Qt.WA_StyledBackground, True)
        connect_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        connect_layout = QVBoxLayout(connect_card)
        connect_layout.setContentsMargins(12, 12, 12, 12)
        connect_layout.setSpacing(8)

        credentials_title = QLabel("CONNECTION SETTINGS")
        credentials_title.setObjectName("sectionTitle")
        credentials_title.setStyleSheet("margin-top: 0px;")
        connect_layout.addWidget(credentials_title)

        connect_grid = QGridLayout()
        connect_grid.setHorizontalSpacing(10)
        connect_grid.setVerticalSpacing(6)
        connect_grid.setColumnStretch(0, 0)
        connect_grid.setColumnStretch(1, 1)
        connect_form = QWidget()
        connect_form.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        connect_form.setLayout(connect_grid)
        connect_layout.addWidget(connect_form)

        token_label = QLabel("PAIR CODE (6 DIGITS)")
        token_label.setObjectName("sectionTitle")
        connect_grid.addWidget(token_label, 0, 0)

        self.token_entry = QLineEdit()
        self.token_entry.setEchoMode(QLineEdit.Password)
        token_row = QHBoxLayout()
        token_row.setSpacing(6)
        token_row.addWidget(self.token_entry, 1)
        self._attach_context_menu(self.token_entry, read_only=False)

        self.show_token_checkbox = QCheckBox("Show")
        self.show_token_checkbox.toggled.connect(self._toggle_show_token)
        token_row.addWidget(self.show_token_checkbox, 0, Qt.AlignVCenter)
        connect_grid.addLayout(token_row, 0, 1)

        server_label = QLabel("SERVER URL")
        server_label.setObjectName("sectionTitle")
        connect_grid.addWidget(server_label, 1, 0)

        self.server_entry = QLineEdit()
        connect_grid.addWidget(self.server_entry, 1, 1)
        self._attach_context_menu(self.server_entry, read_only=False)

        device_id_label = QLabel("DEVICE ID")
        device_id_label.setObjectName("sectionTitle")
        connect_grid.addWidget(device_id_label, 2, 0)
        self.device_id_entry = QLineEdit()
        self.device_id_entry.setMinimumWidth(320)
        connect_grid.addWidget(self.device_id_entry, 2, 1)
        self._attach_context_menu(self.device_id_entry, read_only=False)

        device_name_label = QLabel("DEVICE NAME")
        device_name_label.setObjectName("sectionTitle")
        connect_grid.addWidget(device_name_label, 3, 0)
        self.device_name_entry = QLineEdit()
        connect_grid.addWidget(self.device_name_entry, 3, 1)
        self._attach_context_menu(self.device_name_entry, read_only=False)

        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 4, 0, 0)
        buttons_row.setSpacing(6)
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
        connect_layout.addStretch(1)
        settings_row.addWidget(connect_card, 3, Qt.AlignTop)

        runtime_card = QFrame()
        runtime_card.setObjectName("card")
        runtime_card.setAttribute(Qt.WA_StyledBackground, True)
        runtime_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        runtime_layout = QVBoxLayout(runtime_card)
        runtime_layout.setContentsMargins(12, 12, 12, 12)
        runtime_layout.setSpacing(8)

        runtime_label = QLabel("RUNTIME OVERVIEW")
        runtime_label.setObjectName("sectionTitle")
        runtime_label.setStyleSheet("margin-top: 0px;")
        runtime_layout.addWidget(runtime_label)

        games_label = QLabel("Tracked games")
        games_label.setObjectName("sectionTitle")
        runtime_layout.addWidget(games_label)

        self.games_box = QTextEdit()
        self.games_box.setObjectName("codePanel")
        self.games_box.setReadOnly(True)
        self.games_box.setMinimumHeight(220)
        runtime_layout.addWidget(self.games_box, 1)
        self._attach_context_menu(self.games_box, read_only=True)

        self.status_label = QLabel("Disconnected")
        self.status_label.setObjectName("statusLine")
        self.status_label.setWordWrap(True)
        runtime_layout.addWidget(self.status_label)
        settings_row.addWidget(runtime_card, 2)

        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(0, 0, 0, 0)
        logs_layout.setSpacing(8)

        logs_card = QFrame()
        logs_card.setObjectName("card")
        logs_card.setAttribute(Qt.WA_StyledBackground, True)
        logs_card_layout = QVBoxLayout(logs_card)
        logs_card_layout.setContentsMargins(12, 12, 12, 12)
        logs_card_layout.setSpacing(8)

        logs_header = QLabel("RUNTIME LOGS")
        logs_header.setObjectName("sectionTitle")
        logs_header.setStyleSheet("margin-top: 0px;")
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
            self._apply_agent_pairing_payload(self.settings_store, valid_server_url, payload or {})
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
