from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, QSettings, Qt

from anidesk.domain.models import Anime, ArchiveRecord, ArchivedAnime, ReminderItem, Season
from anidesk.services.covers import CoverCache
from anidesk.ui.controller import AppController
from anidesk.ui.main_window import MainWindow
from anidesk.ui.overlay import ReminderOverlay


def test_main_window_has_four_pages_and_hides_to_tray(qtbot, tmp_path: Path) -> None:
    window = MainWindow(CoverCache(tmp_path / "covers"))
    qtbot.addWidget(window)
    window.show()
    assert window.stack.count() == 4
    window.close()
    assert not window.isVisible()


def test_season_combo_returns_season_enum(qtbot, tmp_path: Path) -> None:
    window = MainWindow(CoverCache(tmp_path / "covers"))
    qtbot.addWidget(window)
    fall_index = list(Season).index(Season.FALL)
    window.season_page.season.setCurrentIndex(fall_index)

    selected = window.season_page.selected_season()

    assert selected is Season.FALL


def test_overlay_keeps_updates_and_uses_reliable_edge_auto_hide(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "overlay.ini"), QSettings.Format.IniFormat)
    overlay = ReminderOverlay(settings)
    qtbot.addWidget(overlay)
    now = datetime.now(UTC)
    yesterday = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    today = now.isoformat().replace("+00:00", "Z")
    first = ReminderItem("1", "a", "作品 A", "", 1, yesterday, None, [], True)
    second = ReminderItem("2", "b", "作品 B", "", 2, today, None, [], False)
    overlay.show_items([first, second])
    assert overlay.current is first
    assert len(overlay.items) == 2
    assert not overlay.isVisible()
    assert overlay.edge_hot_zone.isValid()
    assert overlay.edge_hot_zone.width() == overlay.HOT_ZONE_WIDTH
    assert overlay._hover_timer.isActive()
    assert overlay._hover_timer.interval() == overlay.HOVER_POLL_MS
    assert overlay.collapsed

    pinned_screen = overlay.pinned_screen_name
    overlay._check_edge_hover(overlay.edge_hot_zone.center())
    assert not overlay.collapsed
    assert overlay.isVisible()
    expanded_position = overlay.pos()

    drag_start = expanded_position + QPoint(30, 15)
    overlay._start_drag(drag_start)
    overlay._drag_to(drag_start + QPoint(-80, 35))
    assert overlay.pos() == expanded_position + QPoint(-80, 35)
    overlay._finish_drag(drag_start + QPoint(-80, 35))
    assert overlay.pinned_screen_name == pinned_screen
    assert settings.value("overlay/screen") == pinned_screen

    overlay._collapse(animate=False)
    assert overlay.collapsed
    assert not overlay.isVisible()
    assert overlay.edge_hot_zone.isValid()
    assert overlay.current is first
    assert overlay._animation.duration() == overlay.ANIMATION_MS

    overlay.set_enabled(False)
    assert not overlay._hover_timer.isActive()
    overlay._check_edge_hover(overlay.edge_hot_zone.center())
    assert not overlay.isVisible()


def test_archive_note_can_be_edited_and_saved_in_page(qtbot, tmp_path: Path) -> None:
    window = MainWindow(CoverCache(tmp_path / "covers"))
    qtbot.addWidget(window)
    anime = Anime("anime:1", None, None, "作品 A", "作品 A")
    archived = ArchivedAnime(anime, ArchiveRecord(anime.id, "2026-08-15", "旧感想"))
    page = window.archive_page
    page.set_items([archived])

    assert page.editor_anime_id == anime.id
    assert page.note_editor.toPlainText() == "旧感想"
    page.finished_editor.setDate(QDate(2026, 8, 16))
    page.note_editor.setPlainText("在平台内修改后的感想")

    with qtbot.waitSignal(page.edit_requested) as emitted:
        page.save_editor.click()

    assert emitted.args == [anime.id, "2026-08-16", "在平台内修改后的感想"]


def test_cover_loader_downloads_every_item_in_progressive_bounded_batches(qtbot, repository) -> None:
    class FakeCoverCache:
        def __init__(self) -> None:
            self.downloaded: set[str] = set()
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def cached(self, _url: str):
            return None

        def get(self, url: str):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.002)
            with self.lock:
                self.downloaded.add(url)
                self.active -= 1
            return Path(url.rsplit("/", 1)[-1])

    covers = FakeCoverCache()
    window = MainWindow(covers)  # type: ignore[arg-type]
    qtbot.addWidget(window)
    controller = AppController(window, repository, covers)  # type: ignore[arg-type]
    items = [
        Anime(f"anime:{index}", None, None, f"作品 {index}", f"Anime {index}", cover_url=f"https://example.test/{index}.jpg")
        for index in range(85)
    ]
    updated: list[str] = []

    controller._cache_covers(items, updated.extend)
    qtbot.waitUntil(lambda: len(updated) == len(items), timeout=5000)

    assert len(covers.downloaded) == 85
    assert set(updated) == {item.id for item in items}
    assert 1 < covers.max_active <= 4
