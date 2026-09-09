"""Offline startup check for validating the portable executable after packaging."""
from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from anidesk import __version__
from anidesk.platform.paths import app_data_dir
from anidesk.platform.windows import resource_path
from anidesk.services.covers import CoverCache
from anidesk.services.appearance import AppearanceStore, SIDEBAR_IMAGES, THEMES
from anidesk.domain.models import Anime, EpisodeSchedule, FollowedAnime, FollowRecord, ArchiveRecord, ReminderItem
from anidesk.storage import SqliteRepository
from anidesk.ui.main_window import MainWindow
from anidesk.ui.overlay import ReminderOverlay
from anidesk.ui.theme import ThemeManager
from anidesk.ui.note_editor import NoteEditor


def run_self_test() -> int:
    """Check bundled resources and widgets without accessing user data or remote APIs."""
    app = QApplication.instance() or QApplication([])
    data = app_data_dir()
    result = {"version": __version__, "data_directory": str(data), "success": False}
    try:
        if QIcon(str(resource_path("icon.ico"))).isNull():
            raise RuntimeError("Packaged icon could not be loaded")
        with tempfile.TemporaryDirectory(prefix="self-test-", dir=data) as directory:
            scratch = Path(directory)
            repository = SqliteRepository(scratch / "test.db")
            repository.initialize()
            if repository.get_following() != []:
                raise RuntimeError("Fresh diagnostic database contains unexpected records")
            covers = CoverCache(scratch / "covers")
            theme = ThemeManager(app, AppearanceStore(scratch))
            window = MainWindow(covers, theme)
            overlay = ReminderOverlay(QSettings(str(scratch / "settings.ini"), QSettings.Format.IniFormat), theme)
            if window.stack.count() != 4:
                raise RuntimeError("Main window pages are incomplete")
            if window.season_page.table.columnCount() != 5:
                raise RuntimeError("Season page weekday column is missing")
            if window.following_page.table.columnCount() != 5:
                raise RuntimeError("Following page columns are incomplete")
            if window.settings_page.tabs.count() != 2:
                raise RuntimeError("Appearance settings are missing")
            for artwork in SIDEBAR_IMAGES:
                if theme.sidebar_image(replace(theme.current, sidebar_source="builtin", sidebar_builtin=artwork)).isNull():
                    raise RuntimeError(f"Bundled sidebar artwork is missing: {artwork}")
            anime = Anime("self-test", None, None, "界面自检", "")
            window.season_page.set_items([anime])
            if len(window.season_page.gallery.cards) != 1:
                raise RuntimeError("Season poster gallery is incomplete")
            repository.upsert_anime(anime)
            note = "长篇感想自检。\n\n保留分段与文字。🌊\n" * 1000
            repository.archive_anime(ArchiveRecord(anime.id, "2026-09-08", note))
            archived = repository.get_archive()
            window.archive_page.set_items(archived)
            editor = NoteEditor(archived[0], window)
            if editor.text.toPlainText() != note or len(window.archive_page.gallery.cards) != 1:
                raise RuntimeError("Long-form review or archive gallery failed")
            editor.close()
            instant = datetime.now().astimezone().isoformat()
            overlay.show_items([ReminderItem("self-test-event", anime.id, "界面自检", "", 1, instant, None, [], True)])
            if overlay.current is None or overlay.width() >= overlay.height():
                raise RuntimeError("Vertical reminder card could not be loaded")
            window.following_page.set_items([FollowedAnime(anime, FollowRecord(anime.id), [
                EpisodeSchedule("self-test-event", anime.id, 1, instant)])])
            if len(window.following_page.board.entries) != 1:
                raise RuntimeError("Weekly calendar could not show a local schedule")
            theme.import_sidebar(resource_path("sidebar/sea.png"))
            if theme.sidebar_image().isNull():
                raise RuntimeError("Custom sidebar image import failed")
            for preset in THEMES:
                theme.preview(replace(theme.current, theme=preset))
                app.processEvents()
                if "$" in app.styleSheet():
                    raise RuntimeError("Theme stylesheet contains unresolved variables")
            theme.apply()
            if AppearanceStore(scratch).load() != theme.current:
                raise RuntimeError("Appearance preferences were not saved correctly")
            result["themes"] = list(THEMES)
            result["sidebar_images"] = list(SIDEBAR_IMAGES)
            result["weekly_calendar"] = True
            result["poster_galleries"] = True
            result["long_review_characters"] = len(note)
            result["vertical_overlay"] = True
            app.processEvents()
            overlay.close()
            window.allow_close = True
            window.close()
            result["success"] = True
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    (data / "self-test.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["success"] else 1
