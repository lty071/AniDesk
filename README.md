# AniDesk Python

AniDesk 的 Python 3.13 + PySide6 Widgets 实现。

## 开发

```powershell
.\.venv\Scripts\python.exe -m pip install -e .\anidesk_py
.\.venv\Scripts\python.exe -m pytest .\anidesk_py\tests
$env:PYTHONPATH = ".\anidesk_py\src"
.\.venv\Scripts\python.exe -m anidesk
```

应用数据保存在 `%LOCALAPPDATA%\AniDesk`。退出主窗口只会隐藏应用，请从托盘菜单彻底退出。

启用悬浮窗后，屏幕右侧会常驻一个贴边的“追更”标签；鼠标移入可查看昨天和今天的更新日程，移出后自动收起。已看仓库中的看完日期和感想可在作品列表右侧直接编辑保存。

季度目录会根据 Bangumi 返回的总数自动分页，封面采用至多四路并发分批缓存，每批完成后立即更新对应列表行。

## 打包

```powershell
cd anidesk_py
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm AniDesk.spec
```

首版仅生成 `onedir` 目录，输出位于 `anidesk_py/dist/AniDesk/`。
