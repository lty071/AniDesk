from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from anidesk.domain.models import Anime
from anidesk.services.covers import CoverCache
from anidesk.services.timeutil import parse_iso


def anime_icon(anime: Anime, cache: CoverCache | None = None) -> QIcon:
    pixmap = QPixmap()
    if anime.cover_data.startswith("data:") and "," in anime.cover_data:
        try:
            pixmap.loadFromData(QByteArray.fromBase64(anime.cover_data.split(",", 1)[1].encode("ascii")))
        except Exception:
            pass
    elif anime.cover_data and Path(anime.cover_data).is_file():
        pixmap.load(anime.cover_data)
    elif cache and anime.cover_url:
        path = cache.cached(anime.cover_url)
        if path:
            pixmap.load(str(path))
    if pixmap.isNull():
        placeholder = QPixmap(54, 72)
        placeholder.fill(Qt.GlobalColor.lightGray)
        pixmap = placeholder
    return QIcon(pixmap.scaled(54, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


def local_time(value: str) -> str:
    if not value:
        return "未获取"
    try:
        return parse_iso(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def configure_table(table: QTableWidget) -> None:
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setIconSize(QSize(54, 72))


def selected_id(table: QTableWidget) -> str | None:
    rows = table.selectionModel().selectedRows()
    if not rows:
        return None
    item = table.item(rows[0].row(), 0)
    return str(item.data(Qt.ItemDataRole.UserRole)) if item else None


def id_item(anime: Anime, cache: CoverCache | None) -> QTableWidgetItem:
    item = QTableWidgetItem(anime_icon(anime, cache), anime.title_cn or anime.title_native)
    item.setData(Qt.ItemDataRole.UserRole, anime.id)
    return item
