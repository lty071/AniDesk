from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class CloudVersion:
    id: str
    name: str
    updated_at: str
    size: int


class CloudSyncProvider(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def upload(self, name: str, data: bytes) -> CloudVersion: ...
    def download(self, version_id: str) -> bytes: ...
    def list_versions(self) -> list[CloudVersion]: ...


class CloudSyncNotConfigured:
    @staticmethod
    def _unavailable() -> None:
        raise RuntimeError("云同步将在第二阶段接入，目前请使用本地备份。")

    def connect(self) -> None: self._unavailable()
    def disconnect(self) -> None: return None
    def upload(self, name: str, data: bytes) -> CloudVersion: self._unavailable(); raise AssertionError
    def download(self, version_id: str) -> bytes: self._unavailable(); raise AssertionError
    def list_versions(self) -> list[CloudVersion]: self._unavailable(); raise AssertionError
