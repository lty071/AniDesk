from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    QTimer,
    Qt,
    Signal,
)
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


class DragHandle(QLabel):
    """Header label that forwards global mouse positions for window dragging."""

    drag_started = Signal(QPoint)
    drag_moved = Signal(QPoint)
    drag_finished = Signal(QPoint)

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.drag_started.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.drag_moved.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.drag_finished.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ReminderOverlay(QWidget):
    """Draggable, screen-pinned update board with QQ-style edge auto-hide."""

    HOT_ZONE_WIDTH = 4
    HOVER_POLL_MS = 80
    ANIMATION_MS = 180

    open_requested = Signal(str)
    snooze_requested = Signal(object)
    dismissed = Signal(object)

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle("AniDesk 近两日追更")
        self.setFixedSize(400, 260)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(
            "QWidget#card{background:#fff;border:1px solid #d45532;border-radius:10px}"
            "QLabel{background:transparent}"
            "QLabel#dragHandle{font-size:17px;font-weight:700;color:#b94729;padding:2px}"
            "QLabel#dragHandle:hover{background:#fff0ea;border-radius:4px}"
            "QListWidget{background:#fff;border:1px solid #e1e5e7;border-radius:5px;padding:2px}"
            "QListWidget::item{padding:5px} QListWidget::item:selected{background:#f3d8ce;color:#7d2d18}"
        )
        self.items: list[ReminderItem] = []
        self.current: ReminderItem | None = None
        self._settings = settings or QSettings()
        self._screen_name = str(self._settings.value("overlay/screen", "") or "")
        stored_side = str(self._settings.value("overlay/side", "right") or "right")
        self._dock_side = stored_side if stored_side in {"left", "right"} else "right"
        try:
            self._dock_offset_y = int(self._settings.value("overlay/y", 24))
        except (TypeError, ValueError):
            self._dock_offset_y = 24
        self._enabled = True
        self._collapsed = True
        self._dragging = False
        self._drag_offset = QPoint()

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(500)
        self._collapse_timer.timeout.connect(self._collapse_if_outside)
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(self.HOVER_POLL_MS)
        self._hover_timer.timeout.connect(self._check_edge_hover)
        self._hover_timer.start()
        self._animation = QPropertyAnimation(self, b"pos", self)
        self._animation.setDuration(self.ANIMATION_MS)
        self._animation.finished.connect(self._animation_finished)
        self._edge_hot_zone = QRect()

        card = QWidget()
        card.setObjectName("card")
        self.drag_handle = DragHandle("近两日追更  ·  拖动调整位置")
        self.drag_handle.setObjectName("dragHandle")
        self.drag_handle.drag_started.connect(self._start_drag)
        self.drag_handle.drag_moved.connect(self._drag_to)
        self.drag_handle.drag_finished.connect(self._finish_drag)
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
        header.addWidget(self.drag_handle, 1)
        header.addWidget(self.count)
        layout.addLayout(header)
        layout.addWidget(self.update_list, 1)
        layout.addWidget(self.title)
        detail_row = QHBoxLayout()
        detail_row.addWidget(self.detail, 1)
        detail_row.addWidget(self.links, 1)
        layout.addLayout(detail_row)
        layout.addLayout(actions)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self._select(-1)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    @property
    def pinned_screen_name(self) -> str:
        screen = self._pinned_screen()
        return screen.name() if screen else ""

    @property
    def edge_hot_zone(self) -> QRect:
        return QRect(self._edge_hot_zone)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._collapse_timer.stop()
        self._animation.stop()
        if not enabled:
            self._hover_timer.stop()
            self.hide()
            return
        self._hover_timer.start()
        self._collapsed = True
        self._place_trigger()
        hidden = self._hidden_position()
        if hidden is not None:
            self.move(hidden)
        self.hide()

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
            self._place_trigger()
            if self._animation.state() != QAbstractAnimation.State.Running:
                target = self._hidden_position() if self._collapsed else self._expanded_position()
                if target is not None:
                    self.move(target)
                self.setVisible(not self._collapsed)

    def enterEvent(self, event) -> None:
        self._collapse_timer.stop()
        self._expand()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._dragging:
            self._collapse_timer.start()
        super().leaveEvent(event)

    def closeEvent(self, event) -> None:
        self._hover_timer.stop()
        self._animation.stop()
        super().closeEvent(event)

    def reveal(self) -> None:
        """Reveal the board from a tray action or another explicit UI entry."""
        self._expand()

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

    def _pinned_screen(self):
        screens = QApplication.screens()
        screen = next((item for item in screens if item.name() == self._screen_name), None)
        if screen is None:
            screen = QApplication.primaryScreen() or (screens[0] if screens else None)
            if screen is not None:
                self._screen_name = screen.name()
        if screen is not None and not self._side_is_exposed(screen, self._dock_side):
            alternate = "left" if self._dock_side == "right" else "right"
            if self._side_is_exposed(screen, alternate):
                self._dock_side = alternate
        return screen

    def _side_is_exposed(self, screen, side: str) -> bool:
        area = screen.availableGeometry()
        maximum = max(0, area.height() - self.height())
        offset_y = max(0, min(self._dock_offset_y, maximum))
        y = area.top() + offset_y
        x = area.left() - self.width() if side == "left" else area.right() + 1
        hidden_rect = QRect(x, y, self.width(), self.height())
        return not any(
            other is not screen and hidden_rect.intersects(other.availableGeometry())
            for other in QApplication.screens()
        )

    def _screen_area(self):
        screen = self._pinned_screen()
        return screen.availableGeometry() if screen else None

    def _clamped_y(self, area) -> int:
        maximum = max(0, area.height() - self.height())
        self._dock_offset_y = max(0, min(self._dock_offset_y, maximum))
        return area.top() + self._dock_offset_y

    def _expanded_position(self) -> QPoint | None:
        area = self._screen_area()
        if area is None:
            return None
        x = area.left() if self._dock_side == "left" else area.right() - self.width() + 1
        return QPoint(x, self._clamped_y(area))

    def _hidden_position(self) -> QPoint | None:
        area = self._screen_area()
        if area is None:
            return None
        x = area.left() - self.width() if self._dock_side == "left" else area.right() + 1
        return QPoint(x, self._clamped_y(area))

    def _place_trigger(self) -> None:
        area = self._screen_area()
        if area is None:
            self._edge_hot_zone = QRect()
            return
        x = area.left() if self._dock_side == "left" else area.right() - self.HOT_ZONE_WIDTH + 1
        self._edge_hot_zone = QRect(x, self._clamped_y(area), self.HOT_ZONE_WIDTH, self.height())

    def _check_edge_hover(self, position: QPoint | None = None) -> None:
        if not self._enabled or not self._collapsed or self._dragging:
            return
        if not self._edge_hot_zone.isValid():
            return
        cursor_position = position if position is not None else QCursor.pos()
        if self._edge_hot_zone.contains(cursor_position):
            self._expand()

    def _animate_to(self, target: QPoint, animate: bool, expanding: bool) -> None:
        self._animation.stop()
        if not animate or self.pos() == target:
            self.move(target)
            self._animation_finished()
            return
        easing = QEasingCurve.Type.OutCubic if expanding else QEasingCurve.Type.InCubic
        self._animation.setEasingCurve(easing)
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(target)
        self._animation.start()

    def _expand(self, animate: bool = True) -> None:
        if not self._enabled or self._dragging:
            return
        target = self._expanded_position()
        start = self._hidden_position()
        if target is None or start is None:
            return
        self._collapse_timer.stop()
        self._animation.stop()
        if not self.isVisible():
            self.move(start)
            self.show()
        self._collapsed = False
        self.raise_()
        self._animate_to(target, animate, expanding=True)

    def _collapse(self, animate: bool = True) -> None:
        if not self._enabled or self._dragging:
            return
        target = self._hidden_position()
        if target is None:
            return
        self._collapse_timer.stop()
        self._collapsed = True
        if not self.isVisible():
            self.move(target)
            self._place_trigger()
            return
        self._animate_to(target, animate, expanding=False)

    def _animation_finished(self) -> None:
        if self._collapsed:
            self.hide()
            self._place_trigger()

    def _collapse_if_outside(self) -> None:
        if self._dragging:
            return
        if self.links.view().isVisible() or self.underMouse():
            self._collapse_timer.start()
            return
        self._collapse()

    def _start_drag(self, global_position: QPoint) -> None:
        if not self._enabled:
            return
        self._animation.stop()
        self._collapse_timer.stop()
        self._collapsed = False
        self._dragging = True
        self._drag_offset = global_position - self.pos()

    def _drag_to(self, global_position: QPoint) -> None:
        if self._dragging:
            self.move(global_position - self._drag_offset)

    def _finish_drag(self, _global_position: QPoint) -> None:
        if not self._dragging:
            return
        screen = QApplication.screenAt(self.frameGeometry().center()) or self._pinned_screen()
        if screen is None:
            self._dragging = False
            return
        self._screen_name = screen.name()
        area = screen.availableGeometry()
        maximum = max(0, area.height() - self.height())
        self._dock_offset_y = max(0, min(self.y() - area.top(), maximum))
        left_distance = abs(self.frameGeometry().left() - area.left())
        right_distance = abs(area.right() - self.frameGeometry().right())
        distances = {"left": left_distance, "right": right_distance}
        exposed = [side for side in ("left", "right") if self._side_is_exposed(screen, side)]
        candidates = exposed or ["left", "right"]
        self._dock_side = min(candidates, key=distances.__getitem__)
        self._save_dock()
        self._dragging = False
        self._collapsed = False
        self._place_trigger()
        target = self._expanded_position()
        if target is not None:
            self._animate_to(target, True, expanding=True)
        self._collapse_timer.start(1200)

    def _save_dock(self) -> None:
        self._settings.setValue("overlay/screen", self._screen_name)
        self._settings.setValue("overlay/side", self._dock_side)
        self._settings.setValue("overlay/y", self._dock_offset_y)
        self._settings.sync()

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
