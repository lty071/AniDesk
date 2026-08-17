from __future__ import annotations

from datetime import date
from uuid import uuid4

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from anidesk.domain.models import Anime, AppSettings, ArchivedAnime, FollowedAnime, Season
from anidesk.services.covers import CoverCache
from anidesk.services.season import SEASON_LABELS, current_season
from .common import anime_icon, configure_table, id_item, local_time, selected_id


def page_header(title: str, subtitle: str) -> tuple[QLabel, QLabel]:
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    description = QLabel(subtitle)
    description.setWordWrap(True)
    description.setStyleSheet("color:#697981")
    return heading, description


class SeasonPage(QWidget):
    refresh_requested = Signal(int, object)
    follow_requested = Signal(str)

    def __init__(self, covers: CoverCache) -> None:
        super().__init__()
        self.covers = covers
        self.items: dict[str, Anime] = {}
        year, season = current_season()
        self.year = QSpinBox()
        self.year.setRange(1960, 2100)
        self.year.setValue(year)
        self.season = QComboBox()
        for value in Season:
            # Qt converts StrEnum user data to a plain string, so store the
            # serialized value deliberately and restore the enum on read.
            self.season.addItem(SEASON_LABELS[value], value.value)
        self.season.setCurrentIndex(list(Season).index(season))
        refresh = QPushButton("刷新目录")
        refresh.setObjectName("primary")
        refresh.clicked.connect(self._refresh)
        follow = QPushButton("追更选中作品")
        follow.clicked.connect(self._follow)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("年份"))
        controls.addWidget(self.year)
        controls.addWidget(QLabel("季度"))
        controls.addWidget(self.season)
        controls.addWidget(refresh)
        controls.addStretch()
        controls.addWidget(follow)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["作品", "原名", "首播日期", "状态"])
        configure_table(self.table)
        self.table.doubleClicked.connect(self._follow)
        heading, description = page_header("本季番剧", "浏览 Bangumi 季度目录；网络失败时继续显示本地缓存。")
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addLayout(controls)
        layout.addWidget(self.table)

    def selected_season(self) -> Season:
        return Season(str(self.season.currentData()))

    def set_items(self, items: list[Anime]) -> None:
        self.items = {item.id: item for item in items}
        self.table.setRowCount(len(items))
        for row, anime in enumerate(items):
            self.table.setRowHeight(row, 78)
            self.table.setItem(row, 0, id_item(anime, self.covers))
            self.table.setItem(row, 1, QTableWidgetItem(anime.title_native))
            self.table.setItem(row, 2, QTableWidgetItem(anime.start_date or "未知"))
            self.table.setItem(row, 3, QTableWidgetItem(anime.status.value))

    def refresh_covers(self, anime_ids: list[str]) -> None:
        changed = set(anime_ids)
        if not changed:
            return
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 0)
            anime_id = str(cell.data(Qt.ItemDataRole.UserRole)) if cell else ""
            anime = self.items.get(anime_id)
            if anime_id in changed and anime is not None:
                cell.setIcon(anime_icon(anime, self.covers))

    def _refresh(self) -> None:
        self.refresh_requested.emit(self.year.value(), self.selected_season())

    def _follow(self) -> None:
        anime_id = selected_id(self.table)
        if anime_id:
            self.follow_requested.emit(anime_id)


class FollowingPage(QWidget):
    sync_requested = Signal(str)
    candidate_requested = Signal(str)
    link_requested = Signal(str, str, str, bool)
    link_default_requested = Signal(object)
    link_delete_requested = Signal(str)
    link_move_requested = Signal(str, int)
    follow_changed = Signal(str, object)
    archive_requested = Signal(str, str, str)
    unfollow_requested = Signal(str)
    open_requested = Signal(str)

    def __init__(self, covers: CoverCache) -> None:
        super().__init__()
        self.covers = covers
        self.items: dict[str, FollowedAnime] = {}
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["作品", "下一集", "提醒", "默认地址", "匹配"])
        configure_table(self.table)
        buttons = QGridLayout()
        for index, (label, callback, primary) in enumerate((
            ("同步日程", self._sync, True),
            ("选择匹配", self._candidate, False),
            ("手动时间", self._manual_time, False),
            ("提醒设置", self._reminder, False),
            ("添加地址", self._add_link, False),
            ("设为默认", self._default_link, False),
            ("地址上移", self._move_link, False),
            ("删除地址", self._delete_link, False),
            ("打开地址", self._open, False),
            ("移入仓库", self._archive, False),
            ("取消追更", self._unfollow, False),
        )):
            button = QPushButton(label)
            if primary:
                button.setObjectName("primary")
            button.clicked.connect(callback)
            buttons.addWidget(button, index // 6, index % 6)
        heading, description = page_header("我的追更", "管理日程、提醒和合法的外部播放地址。")
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addLayout(buttons)
        layout.addWidget(self.table)

    def set_items(self, items: list[FollowedAnime]) -> None:
        self.items = {item.anime.id: item for item in items}
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.table.setRowHeight(row, 78)
            automatic = sorted(item.schedules, key=lambda value: value.air_at)[0] if item.schedules else None
            air_at = item.follow.manual_air_at or (automatic.air_at if automatic else "")
            episode = automatic.episode if automatic else 0
            default = next((link for link in item.links if link.is_default), None)
            self.table.setItem(row, 0, id_item(item.anime, self.covers))
            self.table.setItem(row, 1, QTableWidgetItem(f"第 {episode} 集 · {local_time(air_at)}" if episode else local_time(air_at)))
            minutes = item.follow.reminder_minutes
            self.table.setItem(row, 2, QTableWidgetItem("关闭" if not item.follow.reminder_enabled else f"提前 {minutes if minutes is not None else '全局'} 分钟"))
            self.table.setItem(row, 3, QTableWidgetItem(default.name if default else "未设置"))
            self.table.setItem(row, 4, QTableWidgetItem(str(item.anime.anilist_id or "待匹配")))

    def _selected(self) -> FollowedAnime | None:
        anime_id = selected_id(self.table)
        return self.items.get(anime_id or "")

    def _sync(self) -> None:
        item = self._selected()
        if item: self.sync_requested.emit(item.anime.id)

    def _candidate(self) -> None:
        item = self._selected()
        if item: self.candidate_requested.emit(item.anime.id)

    def _manual_time(self) -> None:
        item = self._selected()
        if not item: return
        value, ok = QInputDialog.getText(self, "手动播出时间", "UTC ISO 8601 时间；留空恢复自动日程", text=item.follow.manual_air_at or "")
        if ok: self.follow_changed.emit(item.anime.id, {"manual_air_at": value.strip() or None, "last_reminded_schedule_id": None})

    def _reminder(self) -> None:
        item = self._selected()
        if not item: return
        enabled = QMessageBox.question(self, "作品提醒", "为该作品启用提醒？") == QMessageBox.StandardButton.Yes
        minutes, ok = QInputDialog.getInt(self, "提前量", "提前多少分钟（0 表示使用全局设置）", item.follow.reminder_minutes or 0, 0, 1440)
        if ok: self.follow_changed.emit(item.anime.id, {"reminder_enabled": enabled, "reminder_minutes": minutes or None})

    def _add_link(self) -> None:
        item = self._selected()
        if not item: return
        url, ok = QInputDialog.getText(self, "添加播放地址", "HTTP/HTTPS 地址")
        if not ok or not url.strip(): return
        name, ok = QInputDialog.getText(self, "地址名称", "名称", text="默认地址" if not item.links else "播放地址")
        if ok: self.link_requested.emit(item.anime.id, name.strip(), url.strip(), not item.links)

    def _open(self) -> None:
        item = self._selected()
        if not item: return
        link = self._choose_link(item, "打开播放地址")
        if link: self.open_requested.emit(link.url)

    def _choose_link(self, item: FollowedAnime, title: str):
        if not item.links:
            QMessageBox.information(self, "播放地址", "该作品尚未添加播放地址。")
            return None
        labels = [f"{'★ ' if link.is_default else ''}{link.name} · {link.url}" for link in item.links]
        choice, ok = QInputDialog.getItem(self, title, "播放地址", labels, 0, False)
        return item.links[labels.index(choice)] if ok else None

    def _default_link(self) -> None:
        item = self._selected()
        if item:
            link = self._choose_link(item, "设为默认地址")
            if link: self.link_default_requested.emit(link)

    def _move_link(self) -> None:
        item = self._selected()
        if item:
            link = self._choose_link(item, "上移播放地址")
            if link: self.link_move_requested.emit(link.id, -1)

    def _delete_link(self) -> None:
        item = self._selected()
        if item:
            link = self._choose_link(item, "删除播放地址")
            if link and QMessageBox.question(self, "删除地址", f"确定删除“{link.name}”？") == QMessageBox.StandardButton.Yes:
                self.link_delete_requested.emit(link.id)

    def _archive(self) -> None:
        item = self._selected()
        if not item: return
        finished, ok = QInputDialog.getText(self, "看完日期", "YYYY-MM-DD", text=date.today().isoformat())
        if not ok: return
        note, ok = QInputDialog.getMultiLineText(self, "感想", "写下感想（可留空）")
        if ok: self.archive_requested.emit(item.anime.id, finished.strip(), note)

    def _unfollow(self) -> None:
        item = self._selected()
        if item and QMessageBox.question(self, "取消追更", f"确定取消追更《{item.anime.title_cn}》？") == QMessageBox.StandardButton.Yes:
            self.unfollow_requested.emit(item.anime.id)


class ArchivePage(QWidget):
    search_requested = Signal(str)
    search_add_requested = Signal(str)
    manual_add_requested = Signal(object)
    edit_requested = Signal(str, str, str)
    restore_requested = Signal(str)
    delete_requested = Signal(str)
    open_requested = Signal(str)
    link_requested = Signal(str, str, str, bool)
    link_default_requested = Signal(object)
    link_delete_requested = Signal(str)
    link_move_requested = Signal(str, int)

    def __init__(self, covers: CoverCache) -> None:
        super().__init__()
        self.covers = covers
        self.items: dict[str, ArchivedAnime] = {}
        self.search_items: dict[str, Anime] = {}
        self.editor_anime_id: str | None = None
        self.query = QLineEdit()
        self.query.setPlaceholderText("搜索过去的番剧")
        search = QPushButton("搜索 Bangumi")
        search.setObjectName("primary")
        search.clicked.connect(lambda: self.search_requested.emit(self.query.text().strip()))
        add_result = QPushButton("将搜索结果加入仓库")
        add_result.clicked.connect(self._add_search)
        manual = QPushButton("手动添加")
        manual.clicked.connect(self._manual)
        search_row = QHBoxLayout()
        search_row.addWidget(self.query)
        search_row.addWidget(search)
        search_row.addWidget(add_result)
        search_row.addWidget(manual)
        self.search_table = QTableWidget(0, 3)
        self.search_table.setHorizontalHeaderLabels(["搜索结果", "原名", "首播日期"])
        configure_table(self.search_table)
        self.search_table.setMaximumHeight(190)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["作品", "看完日期", "感想", "来源"])
        configure_table(self.table)
        self.table.itemSelectionChanged.connect(self._load_editor)
        actions = QGridLayout()
        for index, (label, callback) in enumerate((
            ("添加地址", self._add_link),
            ("设为默认", self._default_link),
            ("地址上移", self._move_link),
            ("删除地址", self._delete_link),
            ("打开地址", self._open),
            ("恢复追更", self._restore),
            ("删除记录", self._delete),
        )):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button, index // 4, index % 4)

        editor = QGroupBox("仓库记录编辑")
        self.editor_title = QLabel("请先选择一部作品")
        self.editor_title.setWordWrap(True)
        self.finished_editor = QDateEdit()
        self.finished_editor.setCalendarPopup(True)
        self.finished_editor.setDisplayFormat("yyyy-MM-dd")
        self.finished_editor.setDate(QDate.currentDate())
        self.note_editor = QTextEdit()
        self.note_editor.setPlaceholderText("在这里直接撰写或修改观后感想…")
        self.note_editor.setMinimumHeight(150)
        self.save_editor = QPushButton("保存日期和感想")
        self.save_editor.setObjectName("primary")
        self.save_editor.setEnabled(False)
        self.save_editor.clicked.connect(self._save_editor)
        editor_form = QFormLayout(editor)
        editor_form.addRow(self.editor_title)
        editor_form.addRow("看完日期", self.finished_editor)
        editor_form.addRow("感想", self.note_editor)
        editor_form.addRow(self.save_editor)

        records = QHBoxLayout()
        records.addWidget(self.table, 2)
        records.addWidget(editor, 1)
        heading, description = page_header("已看仓库", "保存看完日期、感想和播放地址，也可搜索或手动添加过去作品。")
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addLayout(search_row)
        layout.addWidget(self.search_table)
        layout.addLayout(actions)
        layout.addLayout(records, 1)

    def set_items(self, items: list[ArchivedAnime]) -> None:
        retained_id = self.editor_anime_id or selected_id(self.table)
        self.items = {item.anime.id: item for item in items}
        self.table.setRowCount(len(items))
        retained_row: int | None = None
        for row, item in enumerate(items):
            self.table.setRowHeight(row, 78)
            self.table.setItem(row, 0, id_item(item.anime, self.covers))
            self.table.setItem(row, 1, QTableWidgetItem(item.archive.finished_at))
            self.table.setItem(row, 2, QTableWidgetItem(item.archive.note))
            self.table.setItem(row, 3, QTableWidgetItem(item.archive.source))
            if item.anime.id == retained_id:
                retained_row = row
        if items:
            self.table.selectRow(retained_row if retained_row is not None else 0)
        else:
            self._clear_editor()

    def set_search_results(self, items: list[Anime]) -> None:
        self.search_items = {item.id: item for item in items}
        self.search_table.setRowCount(len(items))
        for row, anime in enumerate(items):
            self.search_table.setRowHeight(row, 64)
            self.search_table.setItem(row, 0, id_item(anime, self.covers))
            self.search_table.setItem(row, 1, QTableWidgetItem(anime.title_native))
            self.search_table.setItem(row, 2, QTableWidgetItem(anime.start_date))

    def _selected(self) -> ArchivedAnime | None:
        return self.items.get(selected_id(self.table) or "")

    def _add_search(self) -> None:
        anime_id = selected_id(self.search_table)
        if anime_id: self.search_add_requested.emit(anime_id)

    def _manual(self) -> None:
        title, ok = QInputDialog.getText(self, "手动添加", "中文名")
        if not ok or not title.strip(): return
        native, ok = QInputDialog.getText(self, "手动添加", "原名（可留空）")
        if not ok: return
        finished, ok = QInputDialog.getText(self, "手动添加", "看完日期 YYYY-MM-DD", text=date.today().isoformat())
        if not ok: return
        note, ok = QInputDialog.getMultiLineText(self, "手动添加", "感想（可留空）")
        if not ok: return
        cover_path, _ = QFileDialog.getOpenFileName(self, "选择本地封面（可取消）", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        self.manual_add_requested.emit({"title_cn": title.strip(), "title_native": native.strip(), "finished_at": finished.strip(), "note": note, "cover_path": cover_path})

    def _load_editor(self) -> None:
        item = self._selected()
        if not item:
            self._clear_editor()
            return
        self.editor_anime_id = item.anime.id
        self.editor_title.setText(f"《{item.anime.title_cn or item.anime.title_native}》")
        finished = QDate.fromString(item.archive.finished_at, "yyyy-MM-dd")
        self.finished_editor.setDate(finished if finished.isValid() else QDate.currentDate())
        self.note_editor.setPlainText(item.archive.note)
        self.save_editor.setEnabled(True)

    def _clear_editor(self) -> None:
        self.editor_anime_id = None
        self.editor_title.setText("请先选择一部作品")
        self.finished_editor.setDate(QDate.currentDate())
        self.note_editor.clear()
        self.save_editor.setEnabled(False)

    def _save_editor(self) -> None:
        if not self.editor_anime_id:
            return
        self.edit_requested.emit(
            self.editor_anime_id,
            self.finished_editor.date().toString("yyyy-MM-dd"),
            self.note_editor.toPlainText(),
        )

    def _open(self) -> None:
        item = self._selected()
        if not item: return
        link = self._choose_link(item, "打开播放地址")
        if link: self.open_requested.emit(link.url)

    def _choose_link(self, item: ArchivedAnime, title: str):
        if not item.links:
            QMessageBox.information(self, "播放地址", "该作品尚未添加播放地址。")
            return None
        labels = [f"{'★ ' if link.is_default else ''}{link.name} · {link.url}" for link in item.links]
        choice, ok = QInputDialog.getItem(self, title, "播放地址", labels, 0, False)
        return item.links[labels.index(choice)] if ok else None

    def _add_link(self) -> None:
        item = self._selected()
        if not item: return
        url, ok = QInputDialog.getText(self, "添加播放地址", "HTTP/HTTPS 地址")
        if not ok or not url.strip(): return
        name, ok = QInputDialog.getText(self, "地址名称", "名称", text="默认地址" if not item.links else "播放地址")
        if ok: self.link_requested.emit(item.anime.id, name.strip(), url.strip(), not item.links)

    def _default_link(self) -> None:
        item = self._selected()
        if item:
            link = self._choose_link(item, "设为默认地址")
            if link: self.link_default_requested.emit(link)

    def _move_link(self) -> None:
        item = self._selected()
        if item:
            link = self._choose_link(item, "上移播放地址")
            if link: self.link_move_requested.emit(link.id, -1)

    def _delete_link(self) -> None:
        item = self._selected()
        if item:
            link = self._choose_link(item, "删除播放地址")
            if link and QMessageBox.question(self, "删除地址", f"确定删除“{link.name}”？") == QMessageBox.StandardButton.Yes:
                self.link_delete_requested.emit(link.id)

    def _restore(self) -> None:
        item = self._selected()
        if item: self.restore_requested.emit(item.anime.id)

    def _delete(self) -> None:
        item = self._selected()
        if item and QMessageBox.question(self, "删除仓库记录", f"确定删除《{item.anime.title_cn}》的仓库记录？") == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(item.anime.id)


class SettingsPage(QWidget):
    save_requested = Signal(object, bool)
    export_requested = Signal(object)
    import_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.reminder = QSpinBox()
        self.reminder.setRange(0, 1440)
        self.notifications = QCheckBox("启用系统通知")
        self.floating = QCheckBox("启用置顶悬浮提醒")
        self.refresh = QSpinBox()
        self.refresh.setRange(1, 168)
        self.autostart = QCheckBox("开机自动启动 AniDesk")
        form = QFormLayout()
        form.addRow("全局提前分钟", self.reminder)
        form.addRow("日程刷新小时", self.refresh)
        form.addRow("通知", self.notifications)
        form.addRow("悬浮窗", self.floating)
        form.addRow("开机自启", self.autostart)
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        following = QPushButton("导出追更备份")
        following.clicked.connect(lambda: self.export_requested.emit("following"))
        archive = QPushButton("导出仓库备份")
        archive.clicked.connect(lambda: self.export_requested.emit("archive"))
        restore = QPushButton("从 .anibackup 恢复")
        restore.clicked.connect(self.import_requested)
        backups = QHBoxLayout()
        backups.addWidget(following)
        backups.addWidget(archive)
        backups.addWidget(restore)
        heading, description = page_header("设置", "提醒、后台同步、开机自启和本地备份。云同步将在第二阶段接入。")
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addLayout(form)
        layout.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(24)
        layout.addWidget(QLabel("<b>本地备份</b>"))
        layout.addLayout(backups)
        layout.addStretch()

    def set_values(self, settings: AppSettings, autostart: bool) -> None:
        self.reminder.setValue(settings.reminder_minutes)
        self.notifications.setChecked(settings.notifications_enabled)
        self.floating.setChecked(settings.floating_window_enabled)
        self.refresh.setValue(settings.refresh_hours)
        self.autostart.setChecked(autostart)

    def _save(self) -> None:
        self.save_requested.emit(
            AppSettings(
                reminder_minutes=self.reminder.value(),
                notifications_enabled=self.notifications.isChecked(),
                floating_window_enabled=self.floating.isChecked(),
                autostart_prompted=True,
                refresh_hours=self.refresh.value(),
            ),
            self.autostart.isChecked(),
        )
