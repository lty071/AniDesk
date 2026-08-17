from __future__ import annotations

import base64
import mimetypes
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from anidesk.domain.models import (
    Anime,
    AnimeStatus,
    AniListCandidate,
    AppSettings,
    ArchiveRecord,
    BackupKind,
    PlaybackLink,
    Season,
)
from anidesk.platform.tasks import TaskRunner
from anidesk.platform.windows import autostart_enabled, open_external, set_autostart
from anidesk.providers import AniListScheduleProvider, BangumiCatalogProvider
from anidesk.services.backup import BackupService
from anidesk.services.covers import CoverCache
from anidesk.services.matching import best_match, score_candidate
from anidesk.services.reminder import ReminderService
from anidesk.services.season import current_season
from anidesk.services.timeutil import utc_now_iso
from anidesk.services.urls import valid_playback_url
from anidesk.storage import SqliteRepository
from .main_window import MainWindow


class AppController(QObject):
    reminders_ready = Signal(object)
    floating_window_visibility_changed = Signal(bool)
    notification_requested = Signal(str, str)
    refresh_interval_changed = Signal(int)

    def __init__(
        self,
        window: MainWindow,
        repository: SqliteRepository,
        covers: CoverCache,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.window = window
        self.repository = repository
        self.covers = covers
        self.catalog = BangumiCatalogProvider()
        self.schedule = AniListScheduleProvider()
        self.backups = BackupService(repository, covers)
        self.runner = TaskRunner(self)
        self.settings = AppSettings()
        self.reminders = ReminderService(repository, lambda: self.settings)
        self.search_results: dict[str, Anime] = {}
        self._connect_pages()

    def _connect_pages(self) -> None:
        season = self.window.season_page
        season.refresh_requested.connect(self.refresh_season)
        season.follow_requested.connect(self.follow)
        following = self.window.following_page
        following.sync_requested.connect(self.sync_one)
        following.candidate_requested.connect(self.choose_candidate)
        following.link_requested.connect(self.save_link)
        following.link_default_requested.connect(self.set_default_link)
        following.link_delete_requested.connect(self.delete_link)
        following.link_move_requested.connect(self.move_link)
        following.follow_changed.connect(self.update_follow)
        following.archive_requested.connect(self.archive_following)
        following.unfollow_requested.connect(self.unfollow)
        following.open_requested.connect(self.open_url)
        archive = self.window.archive_page
        archive.search_requested.connect(self.search_archive)
        archive.search_add_requested.connect(self.add_search_result)
        archive.manual_add_requested.connect(self.add_manual)
        archive.edit_requested.connect(self.edit_archive)
        archive.restore_requested.connect(self.restore_archive)
        archive.delete_requested.connect(self.delete_archive)
        archive.open_requested.connect(self.open_url)
        archive.link_requested.connect(self.save_link)
        archive.link_default_requested.connect(self.set_default_link)
        archive.link_delete_requested.connect(self.delete_link)
        archive.link_move_requested.connect(self.move_link)
        settings = self.window.settings_page
        settings.save_requested.connect(self.save_settings)
        settings.export_requested.connect(self.export_backup)
        settings.import_requested.connect(self.import_backup)

    def start(self) -> None:
        self._busy("正在初始化本地数据库…")
        year = self.window.season_page.year.value()
        season = self.window.season_page.selected_season()

        def initialize():
            self.repository.initialize()
            settings = self.repository.get_settings()
            return (
                settings,
                self.repository.get_season(year, season),
                self.repository.get_following(),
                self.repository.get_archive(),
            )

        self.runner.submit(initialize, on_result=self._started, on_error=self._error)

    def _started(self, result) -> None:
        self.settings, catalog, following, archive = result
        self.window.season_page.set_items(catalog)
        self.window.following_page.set_items(following)
        self.window.archive_page.set_items(archive)
        self.window.settings_page.set_values(self.settings, autostart_enabled())
        self.refresh_interval_changed.emit(self.settings.refresh_hours)
        self.floating_window_visibility_changed.emit(self.settings.floating_window_enabled)
        self._ready("本地数据已载入")
        if not self.settings.autostart_prompted:
            enabled = QMessageBox.question(
                self.window,
                "开机自启",
                "是否在登录 Windows 后自动启动 AniDesk？",
            ) == QMessageBox.StandardButton.Yes
            self.settings.autostart_prompted = True
            set_autostart(enabled)
            self.runner.submit(lambda: self.repository.save_settings(self.settings), on_error=self._error)
            self.window.settings_page.set_values(self.settings, enabled)
        self.refresh_season(self.window.season_page.year.value(), self.window.season_page.selected_season())
        self.sync_all()

    def refresh_season(self, year: int, season: Season) -> None:
        self._busy("正在刷新 Bangumi 季度目录…")

        def work():
            try:
                remote = self.catalog.list_season(year, season)
                self.repository.upsert_anime(remote)
                return self.repository.get_season(year, season), None
            except Exception as error:
                cached = self.repository.get_season(year, season)
                if cached:
                    return cached, "网络刷新失败，正在显示上次缓存。"
                raise error

        def done(result):
            items, notice = result
            self.window.season_page.set_items(items)
            self._ready(notice or f"已载入 {len(items)} 部作品")
            self._cache_covers(items, self.window.season_page.refresh_covers)

        self.runner.submit(work, on_result=done, on_error=self._error)

    def _cache_covers(self, items: list[Anime], callback=None) -> None:
        pending_by_url: dict[str, list[str]] = {}
        for anime in items:
            if anime.cover_url and not self.covers.cached(anime.cover_url):
                pending_by_url.setdefault(anime.cover_url, []).append(anime.id)
        batches = [list(pending_by_url.items())[index : index + 6] for index in range(0, len(pending_by_url), 6)]
        state = {"next": 0, "active": 0}

        def download(batch: list[tuple[str, list[str]]]) -> list[str]:
            downloaded: list[str] = []
            for url, anime_ids in batch:
                try:
                    self.covers.get(url)
                except Exception:
                    continue
                downloaded.extend(anime_ids)
            return downloaded

        def launch() -> None:
            while state["active"] < 4 and state["next"] < len(batches):
                batch = batches[state["next"]]
                state["next"] += 1
                state["active"] += 1

                def finished() -> None:
                    state["active"] -= 1
                    launch()

                self.runner.submit(
                    lambda batch=batch: download(batch),
                    on_result=lambda anime_ids: callback(anime_ids) if callback and anime_ids else None,
                    on_finished=finished,
                )

        launch()

    def follow(self, anime_id: str) -> None:
        anime = self.window.season_page.items.get(anime_id)
        if not anime:
            return
        self._busy(f"正在追更《{anime.title_cn}》…")

        def work():
            self.repository.upsert_anime(anime)
            self.repository.follow_anime(anime.id)
            try:
                self.covers.get(anime.cover_url)
            except Exception:
                pass
            candidates = self._sync_one_auto(anime.id)
            return self.repository.get_following(), candidates

        def done(result):
            following, candidates = result
            self.window.following_page.set_items(following)
            self._ready(f"已追更《{anime.title_cn}》")
            if candidates:
                self._candidate_dialog(anime.id, candidates)

        self.runner.submit(work, on_result=done, on_error=self._error)

    def _sync_one_auto(self, anime_id: str) -> list[AniListCandidate]:
        anime = self.repository.get_anime(anime_id)
        if not anime:
            return []
        anilist_id = anime.anilist_id
        candidates: list[AniListCandidate] = []
        if anilist_id is None:
            candidates = self.schedule.find_candidates(anime)
            match = best_match(anime, candidates)
            if not match.accepted or not match.candidate:
                return candidates
            anilist_id = match.candidate.id
            self.repository.upsert_anime(replace(anime, anilist_id=anilist_id, updated_at=utc_now_iso()))
        schedules = self.schedule.get_schedule(anime_id, anilist_id)
        self.repository.replace_schedules(anime_id, schedules)
        return []

    def sync_one(self, anime_id: str) -> None:
        self._busy("正在同步 AniList 日程…")

        def done(candidates):
            self._reload_collections()
            self._ready("日程同步完成" if not candidates else "需要手动选择 AniList 候选")
            if candidates:
                self._candidate_dialog(anime_id, candidates)

        self.runner.submit(lambda: self._sync_one_auto(anime_id), on_result=done, on_error=self._error)

    def sync_all(self) -> None:
        def work():
            success = 0
            for item in self.repository.get_following():
                try:
                    candidates = self._sync_one_auto(item.anime.id)
                    if not candidates:
                        success += 1
                except Exception:
                    continue
            return success, self.repository.get_following()

        def done(result):
            success, items = result
            self.window.following_page.set_items(items)
            self._ready(f"后台日程同步完成：{success} 部")
            self.check_reminders()

        self.runner.submit(work, on_result=done)

    def choose_candidate(self, anime_id: str) -> None:
        owner = self.window.following_page.items.get(anime_id)
        anime = owner.anime if owner else None
        if not anime:
            return
        self._busy("正在查询 AniList 候选…")
        self.runner.submit(
            lambda: self.schedule.find_candidates(anime),
            on_result=lambda values: self._candidate_dialog(anime_id, values),
            on_error=self._error,
        )

    def _candidate_dialog(self, anime_id: str, candidates: list[AniListCandidate]) -> None:
        owner = self.window.following_page.items.get(anime_id)
        anime = owner.anime if owner else None
        if not anime or not candidates:
            self._ready("没有找到 AniList 候选，可使用手动播出时间")
            return
        labels = []
        for candidate in candidates:
            scored = score_candidate(anime, candidate)
            title = candidate.title_native or candidate.title_romaji or candidate.title_english
            labels.append(f"{title} · {candidate.start_date or '日期未知'} · {scored.score} 分")
        choice, ok = QInputDialog.getItem(self.window, "选择 AniList 候选", "候选作品", labels, 0, False)
        if ok:
            self._apply_candidate(anime_id, candidates[labels.index(choice)])

    def _apply_candidate(self, anime_id: str, candidate: AniListCandidate) -> None:
        def work():
            anime = self.repository.get_anime(anime_id)
            if not anime:
                raise KeyError(anime_id)
            self.repository.upsert_anime(replace(anime, anilist_id=candidate.id, updated_at=utc_now_iso()))
            self.repository.replace_schedules(anime_id, self.schedule.get_schedule(anime_id, candidate.id))
            return self.repository.get_following()

        self.runner.submit(work, on_result=lambda items: self.window.following_page.set_items(items), on_error=self._error)

    def update_follow(self, anime_id: str, changes: dict[str, object]) -> None:
        self.runner.submit(
            lambda: (self.repository.update_follow(anime_id, **changes), self.repository.get_following())[1],
            on_result=lambda items: self.window.following_page.set_items(items),
            on_error=self._error,
        )

    def save_link(self, anime_id: str, name: str, url: str, make_default: bool) -> None:
        if not valid_playback_url(url):
            self._error(ValueError("请输入有效的 HTTP/HTTPS 地址"))
            return

        def work():
            owners = self.repository.get_following() + self.repository.get_archive()
            owner = next((item for item in owners if item.anime.id == anime_id), None)
            links = owner.links if owner else []
            existing = next((item for item in links if item.url.casefold() == url.casefold()), None)
            self.repository.save_playback_link(
                PlaybackLink(
                    id=existing.id if existing else str(uuid4()),
                    anime_id=anime_id,
                    name=name or url.split("/", 3)[2],
                    url=url,
                    sort_order=existing.sort_order if existing else len(links),
                    is_default=make_default or not links,
                    updated_at=utc_now_iso(),
                )
            )
            return self.repository.get_following(), self.repository.get_archive()

        def done(result):
            following, archive = result
            self.window.following_page.set_items(following)
            self.window.archive_page.set_items(archive)
            self._ready("播放地址已保存")

        self.runner.submit(work, on_result=done, on_error=self._error)

    def set_default_link(self, link: PlaybackLink) -> None:
        updated = replace(link, is_default=True, updated_at=utc_now_iso())

        def work():
            self.repository.save_playback_link(updated)
            return self.repository.get_following(), self.repository.get_archive()

        self.runner.submit(work, on_result=self._collections_result, on_error=self._error)

    def delete_link(self, link_id: str) -> None:
        def work():
            self.repository.delete_playback_link(link_id)
            return self.repository.get_following(), self.repository.get_archive()

        self.runner.submit(work, on_result=self._collections_result, on_error=self._error)

    def move_link(self, link_id: str, direction: int) -> None:
        def work():
            owners = self.repository.get_following() + self.repository.get_archive()
            owner = next((item for item in owners if any(link.id == link_id for link in item.links)), None)
            if owner is None:
                raise KeyError("播放地址不存在")
            links = sorted(owner.links, key=lambda item: (item.sort_order, item.id))
            index = next(index for index, link in enumerate(links) if link.id == link_id)
            target = max(0, min(len(links) - 1, index + direction))
            if target != index:
                current, other = links[index], links[target]
                now = utc_now_iso()
                self.repository.save_playback_link(replace(current, sort_order=other.sort_order, updated_at=now))
                self.repository.save_playback_link(replace(other, sort_order=current.sort_order, updated_at=now))
            return self.repository.get_following(), self.repository.get_archive()

        self.runner.submit(work, on_result=self._collections_result, on_error=self._error)

    def archive_following(self, anime_id: str, finished_at: str, note: str) -> None:
        self._archive(anime_id, finished_at, note, "followed")

    def _archive(self, anime_id: str, finished_at: str, note: str, source: str) -> None:
        try:
            date.fromisoformat(finished_at)
        except ValueError:
            self._error(ValueError("看完日期必须为 YYYY-MM-DD"))
            return

        def work():
            self.repository.archive_anime(ArchiveRecord(anime_id, finished_at, note, source, utc_now_iso()))
            return self.repository.get_following(), self.repository.get_archive()

        self.runner.submit(work, on_result=self._collections_result, on_error=self._error)

    def unfollow(self, anime_id: str) -> None:
        self.runner.submit(
            lambda: (self.repository.unfollow_anime(anime_id), self.repository.get_following())[1],
            on_result=lambda items: self.window.following_page.set_items(items),
            on_error=self._error,
        )

    def search_archive(self, query: str) -> None:
        if not query:
            return
        self._busy("正在搜索 Bangumi…")

        def done(items):
            self.search_results = {item.id: item for item in items}
            self.window.archive_page.set_search_results(items)
            self._ready(f"找到 {len(items)} 条结果")

        self.runner.submit(lambda: self.catalog.search(query), on_result=done, on_error=self._error)

    def add_search_result(self, anime_id: str) -> None:
        anime = self.search_results.get(anime_id)
        if not anime:
            return

        def work():
            self.repository.upsert_anime(anime)
            self.repository.archive_anime(ArchiveRecord(anime.id, date.today().isoformat(), "", "searched", utc_now_iso()))
            try:
                self.covers.get(anime.cover_url)
            except Exception:
                pass
            return self.repository.get_archive()

        self.runner.submit(work, on_result=lambda items: self.window.archive_page.set_items(items), on_error=self._error)

    def add_manual(self, values: dict[str, str]) -> None:
        try:
            finished = date.fromisoformat(values["finished_at"])
        except ValueError:
            self._error(ValueError("看完日期必须为 YYYY-MM-DD"))
            return
        year, season = current_season(finished)
        cover_path = Path(values.get("cover_path") or "")

        def work():
            cover_data = ""
            if cover_path.is_file():
                content = cover_path.read_bytes()
                if len(content) > 15 * 1024 * 1024:
                    raise ValueError("本地封面超过 15 MB")
                mime = mimetypes.guess_type(cover_path.name)[0] or "image/jpeg"
                cover_data = f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
            anime = Anime(
                id=str(uuid4()),
                bgm_id=None,
                anilist_id=None,
                title_cn=values["title_cn"],
                title_native=values["title_native"],
                season_year=year,
                season=season,
                status=AnimeStatus.FINISHED,
                cover_data=cover_data,
                updated_at=utc_now_iso(),
            )
            self.repository.upsert_anime(anime)
            self.repository.archive_anime(ArchiveRecord(anime.id, finished.isoformat(), values["note"], "manual", utc_now_iso()))
            return self.repository.get_archive()

        self.runner.submit(work, on_result=lambda items: self.window.archive_page.set_items(items), on_error=self._error)

    def edit_archive(self, anime_id: str, finished_at: str, note: str) -> None:
        item = self.window.archive_page.items.get(anime_id)
        self._archive(anime_id, finished_at, note, item.archive.source if item else "manual")

    def restore_archive(self, anime_id: str) -> None:
        def work():
            self.repository.restore_from_archive(anime_id)
            try:
                self._sync_one_auto(anime_id)
            except Exception:
                pass
            return self.repository.get_following(), self.repository.get_archive()

        self.runner.submit(work, on_result=self._collections_result, on_error=self._error)

    def delete_archive(self, anime_id: str) -> None:
        self.runner.submit(
            lambda: (self.repository.delete_archive(anime_id), self.repository.get_archive())[1],
            on_result=lambda items: self.window.archive_page.set_items(items),
            on_error=self._error,
        )

    def save_settings(self, settings: AppSettings, autostart: bool) -> None:
        try:
            set_autostart(autostart)
        except Exception as error:
            self._error(error)
            return
        self.settings = settings
        self.refresh_interval_changed.emit(settings.refresh_hours)
        self.floating_window_visibility_changed.emit(settings.floating_window_enabled)
        self.check_reminders()
        self.runner.submit(lambda: self.repository.save_settings(settings), on_result=lambda _v: self._ready("设置已保存"), on_error=self._error)

    def export_backup(self, kind_value: str) -> None:
        kind = BackupKind(kind_value)
        stamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        filename, _ = QFileDialog.getSaveFileName(
            self.window,
            "导出 AniDesk 备份",
            f"{kind.value}-{stamp}.anibackup",
            "AniDesk 备份 (*.anibackup)",
        )
        if not filename:
            return
        self._busy("正在生成备份…")
        self.runner.submit(
            lambda: self.backups.export_file(kind, Path(filename)),
            on_result=lambda path: self._ready(f"备份已保存：{path}"),
            on_error=self._error,
        )

    def import_backup(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self.window, "恢复 AniDesk 备份", "", "AniDesk 备份 (*.anibackup)")
        if not filename:
            return
        self._busy("正在校验并导入备份…")

        def work():
            result = self.backups.import_file(Path(filename))
            return result, self.repository.get_following(), self.repository.get_archive()

        def done(value):
            result, following, archive = value
            self.window.following_page.set_items(following)
            self.window.archive_page.set_items(archive)
            self._ready(f"导入完成：新增 {result['imported']}，合并 {result['merged']}")

        self.runner.submit(work, on_result=done, on_error=self._error)

    def check_reminders(self) -> None:
        def done(result):
            reminders, updates = result
            for item in reminders:
                if self.settings.notifications_enabled:
                    episode = f"第 {item.episode} 集" if item.episode else "新一集"
                    body = f"{episode}已经播出" if item.already_aired else f"{episode}即将播出"
                    self.notification_requested.emit(item.title, body)
            if self.settings.floating_window_enabled:
                self.reminders_ready.emit(updates)

        self.runner.submit(self.reminders.check_with_updates, on_result=done, on_error=self._error)

    def snooze_reminder(self, item) -> None:
        self.runner.submit(lambda: self.reminders.snooze(item), on_error=self._error)

    def open_reminder(self, item) -> None:
        if item.default_url:
            self.open_url(item.default_url)

    def open_url(self, url: str) -> None:
        try:
            if not open_external(url):
                raise RuntimeError("系统未能打开该地址")
        except Exception as error:
            self._error(error)

    def _reload_collections(self) -> None:
        self.runner.submit(
            lambda: (self.repository.get_following(), self.repository.get_archive()),
            on_result=self._collections_result,
            on_error=self._error,
        )

    def _collections_result(self, result) -> None:
        following, archive = result
        self.window.following_page.set_items(following)
        self.window.archive_page.set_items(archive)
        self._ready("本地数据已更新")

    def _busy(self, message: str) -> None:
        self.window.statusBar().showMessage(message)

    def _ready(self, message: str) -> None:
        self.window.statusBar().showMessage(message, 8000)

    def _error(self, error: Exception) -> None:
        self.window.statusBar().showMessage(str(error), 10000)
        QMessageBox.critical(self.window, "AniDesk", str(error))
