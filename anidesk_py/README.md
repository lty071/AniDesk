# AniDesk Python

AniDesk 的 Python 3.13 + PySide6 Widgets 实现。现有 Tauri 代码保留在仓库根目录，作为功能和备份格式的兼容参照。

## 开发

```powershell
.\.venv\Scripts\python.exe -m pip install -e .\anidesk_py
.\.venv\Scripts\python.exe -m pytest .\anidesk_py\tests
$env:PYTHONPATH = ".\anidesk_py\src"
.\.venv\Scripts\python.exe -m anidesk
```

应用数据保存在 `%LOCALAPPDATA%\AniDesk`。退出主窗口只会隐藏应用，请从托盘菜单彻底退出。

启用悬浮窗后，可拖动标题栏将看板吸附到任一屏幕的左侧或右侧；收起时窗口完全移出屏幕，程序会检测鼠标是否进入对应边缘区域并平滑展开，也可从托盘菜单选择“显示追更悬浮窗”。看板固定在所选屏幕，不会随鼠标跨屏漂移。已看仓库中的看完日期和感想可在作品列表右侧直接编辑保存。

季度目录会根据 Bangumi 返回的总数自动分页，封面采用至多四路并发分批缓存，每批完成后立即更新对应列表行。

## 打包

```powershell
cd anidesk_py
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm AniDesk.spec
```

首版仅生成 `onedir` 目录，输出位于 `anidesk_py/dist/AniDesk/`。
