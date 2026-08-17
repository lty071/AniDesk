from __future__ import annotations

import logging
import sys
from importlib import resources
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QCoreApplication, QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from anidesk import __version__
from anidesk.platform.paths import log_dir
from anidesk.platform.windows import SingleInstance, resource_path
from anidesk.services.covers import CoverCache
from anidesk.storage import SqliteRepository
from anidesk.ui.controller import AppController
from anidesk.ui.main_window import MainWindow
from anidesk.ui.overlay import ReminderOverlay


def _configure_logging() -> None:
    target = log_dir() / "anidesk.log"
    handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _stylesheet() -> str:
    return resources.files("anidesk.resources").joinpath("style.qss").read_text(encoding="utf-8")


def main() -> int:
    _configure_logging()
    QCoreApplication.setOrganizationName("AniDesk")
    QCoreApplication.setOrganizationDomain("com.anidesk.desktop")
    QCoreApplication.setApplicationName("AniDesk")
    QCoreApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(_stylesheet())
    icon_path = resource_path("icon.ico")
    icon = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
    app.setWindowIcon(icon)
    covers = CoverCache()
    window = MainWindow(covers)
    window.setWindowIcon(icon)
    instance = SingleInstance()
    if not instance.acquire(window.show_and_activate):
        return 0
    repository = SqliteRepository()
    controller = AppController(window, repository, covers, app)
    overlay = ReminderOverlay()
    overlay.setWindowIcon(icon)
    overlay.open_requested.connect(controller.open_url)
    overlay.snooze_requested.connect(controller.snooze_reminder)
    controller.reminders_ready.connect(overlay.show_items)
    controller.floating_window_visibility_changed.connect(overlay.set_enabled)
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("AniDesk · 桌面追番")
    menu = QMenu()
    show_action = QAction("显示 AniDesk", menu)
    show_action.triggered.connect(window.show_and_activate)
    quit_action = QAction("退出", menu)

    def quit_application() -> None:
        window.allow_close = True
        tray.hide()
        overlay.close()
        window.close()
        app.quit()

    quit_action.triggered.connect(quit_application)
    menu.addAction(show_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show_and_activate()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    controller.notification_requested.connect(
        lambda title, body: tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 10000)
    )
    first_hide = {"shown": False}

    def hidden_notice() -> None:
        if not first_hide["shown"]:
            tray.showMessage("AniDesk 仍在运行", "可从系统托盘重新打开或彻底退出。")
            first_hide["shown"] = True

    window.hidden_to_tray.connect(hidden_notice)
    reminder_timer = QTimer(app)
    reminder_timer.setInterval(60_000)
    reminder_timer.timeout.connect(controller.check_reminders)
    reminder_timer.start()
    sync_timer = QTimer(app)
    sync_timer.timeout.connect(controller.sync_all)
    controller.refresh_interval_changed.connect(lambda hours: sync_timer.start(max(1, hours) * 3_600_000))
    app.applicationStateChanged.connect(
        lambda state: controller.check_reminders() if state == Qt.ApplicationState.ApplicationActive else None
    )
    tray.show()
    window.show()
    QTimer.singleShot(0, controller.start)
    QTimer.singleShot(2000, controller.check_reminders)
    return app.exec()
