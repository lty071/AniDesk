from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from anidesk.domain.models import ReminderItem
from anidesk.services.timeutil import parse_iso


class ReminderOverlay(QWidget):
    """Always-on, edge-collapsing board for yesterday's and today's updates."""

    HANDLE_WIDTH = 26
    EDGE_MARGIN = 12

    open_requested = Signal(str)
    snooze_requested = Signal(object)
    dismissed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AniDesk 近两日追更")
        self.setFixedSize(400, 260)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            "QWidget#card{background:#fff;border:1px solid #d45532;border-radius:10px}"
            "QLabel{background:transparent}"
            "QLabel#edgeHandle{background:#d45532;color:white;font-weight:700;border-radius:7px 0 0 7px}"
            "QListWidget{background:#fff;border:1px solid #e1e5e7;border-radius:5px;padding:2px}"
            "QListWidget::item{padding:5px} QListWidget::item:selected{background:#f3d8ce;color:#7d2d18}"
        )
        self.items: list[ReminderItem] = []
        self.current: ReminderItem | None = None
        self._enabled = True
        self._collapsed = True
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(650)
        self._collapse_timer.timeout.connect(self._collapse_if_outside)

        card = QWidget()
        card.setObjectName("card")
        heading = QLabel("近两日追更")
        heading.setStyleSheet("font-size:17px;font-weight:700;color:#b94729")
        self.count = QLabel("正在读取更新日程…")
        self.count.setStyleSheet("color:#697981")
        self.update_list = QListWidget()
        self.update_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.update_list.currentRowChanged.connect(self._select)
        self.title = QLabel("暂无更新")
        self.title.setStyleSheet("font-weight:700;color:#394850")
        self.detail = QLabel("昨天和今天的追更作品会显示在这里")
        self.detail.setStyleSheet("color:#697981")
        self.links = QComboBox()
        self.open_button = QPushButton("打开地址")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self._open)
        self.snooze_button = QPushButton("延后提醒")
        self.snooze_button.clicked.connect(self._snooze)
        hide = QPushButton("贴边隐藏")
        hide.clicked.connect(self._dismiss)

        actions = QHBoxLayout()
        actions.addWidget(self.open_button)
        actions.addWidget(self.snooze_button)
        actions.addWidget(hide)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        header = QHBoxLayout()
        header.addWidget(heading)
        header.addStretch()
        header.addWidget(self.count)
        layout.addLayout(header)
        layout.addWidget(self.update_list, 1)
        layout.addWidget(self.title)
        detail_row = QHBoxLayout()
        detail_row.addWidget(self.detail, 1)
        detail_row.addWidget(self.links, 1)
        layout.addLayout(detail_row)
        layout.addLayout(actions)

        handle = QLabel("追\n更")
        handle.setObjectName("edgeHandle")
        handle.setFixedWidth(self.HANDLE_WIDTH)
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(card, 1)
        outer.addWidget(handle)
        self._select(-1)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self.hide()
            return
        self.show()
        self._collapse()

    def show_items(self, items: list[ReminderItem]) -> None:
        selected_id = self.current.schedule_id if self.current else None
        self.items = list(items)
        self.update_list.clear()
        today = datetime.now().astimezone().date()
        yesterday_count = 0
        today_count = 0
        selected_row = 0
        for row, item in enumerate(self.items):
            local_air = parse_iso(item.air_at).astimezone()
            if local_air.date() == today - timedelta(days=1):
                day_label = "昨天"
                yesterday_count += 1
            elif local_air.date() == today:
                day_label = "今天"
                today_count += 1
            else:
                day_label = local_air.strftime("%m-%d")
            episode = f"第 {item.episode} 集" if item.episode else "新一集"
            self.update_list.addItem(
                QListWidgetItem(f"{day_label} {local_air:%H:%M}  ·  {episode}  ·  {item.title}")
            )
            if item.schedule_id == selected_id:
                selected_row = row
        if self.items:
            self.count.setText(f"昨天 {yesterday_count} · 今天 {today_count}")
            self.update_list.setCurrentRow(selected_row)
        else:
            placeholder = QListWidgetItem("昨天和今天暂无已获取的更新日程")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.update_list.addItem(placeholder)
            self.count.setText("暂无更新")
            self._select(-1)
        if self._enabled:
            self.show()
            self._place()

    def enterEvent(self, event) -> None:
        self._collapse_timer.stop()
        self._expand()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._collapse_timer.start()
        super().leaveEvent(event)

    def _select(self, row: int) -> None:
        self.current = self.items[row] if 0 <= row < len(self.items) else None
        self.links.clear()
        if self.current is None:
            self.title.setText("暂无更新")
            self.detail.setText("昨天和今天的追更作品会显示在这里")
            self.open_button.setEnabled(False)
            self.snooze_button.setEnabled(False)
            return
        item = self.current
        local_air = parse_iso(item.air_at).astimezone()
        today = datetime.now().astimezone().date()
        day_label = "昨天" if local_air.date() == today - timedelta(days=1) else "今天"
        state = "已更新" if item.already_aired else "预计更新"
        self.title.setText(item.title)
        self.detail.setText(f"{day_label} {local_air:%H:%M} {state}")
        ordered = sorted(item.links, key=lambda link: (not link.is_default, link.sort_order))
        for link in ordered:
            self.links.addItem(f"{'★ ' if link.is_default else ''}{link.name}", link.url)
        self.open_button.setEnabled(bool(ordered))
        self.snooze_button.setEnabled(True)

    def _screen_area(self):
        screen = QApplication.screenAt(QCursor.pos()) or self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry() if screen else None

    def _place(self) -> None:
        area = self._screen_area()
        if area is None:
            return
        if self._collapsed:
            x = area.right() - self.HANDLE_WIDTH + 1
        else:
            x = area.right() - self.width() - self.EDGE_MARGIN + 1
        self.move(x, area.top() + 24)

    def _expand(self) -> None:
        if not self._enabled:
            return
        self._collapsed = False
        self._place()
        self.raise_()

    def _collapse(self) -> None:
        if not self._enabled:
            return
        self._collapsed = True
        self._place()

    def _collapse_if_outside(self) -> None:
        if self.links.view().isVisible() or self.underMouse():
            self._collapse_timer.start()
            return
        self._collapse()

    def _open(self) -> None:
        url = self.links.currentData()
        if url:
            self.open_requested.emit(str(url))

    def _snooze(self) -> None:
        if self.current:
            self.snooze_requested.emit(self.current)
        self._collapse()

    def _dismiss(self) -> None:
        if self.current:
            self.dismissed.emit(self.current)
        self._collapse()
