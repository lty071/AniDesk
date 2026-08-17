from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx

from anidesk.platform.paths import cover_cache_dir


class CoverCache:
    def __init__(self, directory: Path | None = None, client: httpx.Client | None = None) -> None:
        self.directory = directory or cover_cache_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(20.0, connect=8.0),
            follow_redirects=True,
            headers={"User-Agent": "AniDesk/0.1.2 (desktop anime tracker)"},
        )
        self._locks_guard = threading.Lock()
        self._download_locks: dict[Path, threading.Lock] = {}

    def path_for(self, url: str) -> Path:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        return self.directory / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}{suffix}"

    def get(self, url: str) -> Path | None:
        if not url:
            return None
        target = self.path_for(url)
        with self._locks_guard:
            download_lock = self._download_locks.setdefault(target, threading.Lock())
        with download_lock:
            if target.is_file() and target.stat().st_size:
                return target
            response = self._client.get(url)
            response.raise_for_status()
            if not response.content:
                raise ValueError("封面文件为空")
            if len(response.content) > 15 * 1024 * 1024:
                raise ValueError("封面文件超过 15 MB")
            temporary = target.with_suffix(target.suffix + ".part")
            temporary.write_bytes(response.content)
            temporary.replace(target)
            return target

    def cached(self, url: str) -> Path | None:
        if not url:
            return None
        target = self.path_for(url)
        return target if target.is_file() and target.stat().st_size else None
