from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from anidesk.services.covers import CoverCache
from .pages import ArchivePage, FollowingPage, SeasonPage, SettingsPage


class MainWindow(QMainWindow):
    hidden_to_tray = Signal()

    def __init__(self, covers: CoverCache) -> None:
        super().__init__()
        self.allow_close = False
        self.setWindowTitle("AniDesk · 桌面追番")
        self.resize(1240, 820)
        self.setMinimumSize(900, 620)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 22, 16, 18)
        brand = QLabel("AniDesk")
        brand.setStyleSheet("font-size:26px;font-weight:800")
        tagline = QLabel("桌面追番")
        tagline.setStyleSheet("color:#aebbc2")
        side_layout.addWidget(brand)
        side_layout.addWidget(tagline)
        side_layout.addSpacing(24)
        self.stack = QStackedWidget()
        self.season_page = SeasonPage(covers)
        self.following_page = FollowingPage(covers)
        self.archive_page = ArchivePage(covers)
        self.settings_page = SettingsPage()
        pages = (
            ("本季番剧", self.season_page),
            ("我的追更", self.following_page),
            ("已看仓库", self.archive_page),
            ("设置", self.settings_page),
        )
        group = QButtonGroup(self)
        group.setExclusive(True)
        for index, (label, page) in enumerate(pages):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=index: self.stack.setCurrentIndex(value))
            group.addButton(button)
            side_layout.addWidget(button)
            self.stack.addWidget(page)
            if index == 0:
                button.setChecked(True)
        side_layout.addStretch()
        side_layout.addWidget(QLabel("v0.1.2 · Local First"))
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack.setContentsMargins(20, 18, 20, 18)
        self.setCentralWidget(root)
        self.statusBar().showMessage("准备就绪")

    def show_and_activate(self) -> None:
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.hidden_to_tray.emit()
