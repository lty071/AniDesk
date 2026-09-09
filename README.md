# AniDesk

AniDesk 是一款面向 Windows 10/11 的本地优先桌面追番工具。它使用 Bangumi 获取中文番剧资料，使用 AniList 补充集数的精确播出时间，并将个人追更、播放地址、看完日期和感想保存在本机 SQLite 数据库中。

当前主版本为 **v0.2.0，Python 3.13 + PySide6 Widgets**，源码位于 `anidesk_py/`。使用说明见 [read.md](read.md)，开发和打包说明见 [anidesk_py/README.md](anidesk_py/README.md)。

## 运行与数据

Windows 发行产物为单文件便携版 `AniDesk-v0.2.0.exe`，文件名自动附带版本号，无需安装 Python，也无需配套 `_internal` 目录。程序启动时会将内置运行库临时解压，首次启动可能需要稍等。

个人数据保存在**实际 exe 所在目录**的 `data/` 中，包括 `anidesk.db`、`covers/`、`backups/`、`logs/`、保存悬浮窗位置的 `settings.ini`、外观配置 `appearance.json` 和背景副本 `themes/backgrounds/`。请将 exe 放在当前用户有写入权限的目录。

首次使用且 `data/anidesk.db` 尚不存在时，程序会优先从旧 Python 版的 `%LOCALAPPDATA%/AniDesk` 复制数据；没有旧 Python 数据库时，再尝试旧 Tauri 版数据。数据库通过 SQLite 快照复制，已有封面和备份也会迁入；原目录保持不变，已有便携版数据库不会被覆盖。以后启动直接使用 `data/`。

升级时先从托盘退出程序，再替换同目录的 exe，保留 `data/`。换电脑或移动完整使用环境时，请一起复制 **`AniDesk.exe` 和 `data/`**。仅分享 exe 不会附带个人记录。

## 开发环境

在本仓库根目录使用 Python 3.13 执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\anidesk_py\requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e "./anidesk_py[dev]"
.\.venv\Scripts\python.exe -m pytest .\anidesk_py\tests
.\.venv\Scripts\python.exe .\anidesk_py\run_anidesk.py
```

源码运行的数据位于 `anidesk_py/data/`，与 `run_anidesk.py` 相邻，不随终端当前目录变化。主窗口关闭后应用仍驻留托盘，请从托盘菜单选择“退出”以彻底结束。

## 主要功能

- v0.1.8：本季番剧采用海报浏览，已看仓库按月份整理；长篇感想在独立页面编辑，支持全屏、Ctrl+S 保存和未保存关闭提示。通用/外观设置采用分组卡片与效果预览，悬浮窗采用竖向日程卡。

- 我的追更默认采用每周放送日历，按本机时区展示真实已获取或手动设置的日程；支持切换周次、查看作品详情和打开所选地址。“全部追更”继续提供完整清单，缺少日程的作品不会丢失。
- 左侧插画内置海风、星空、樱花三种，支持本地图片、缩放、画面位置和顶部渐隐。更换入口仅位于“设置 → 外观 → 侧栏图片”，侧栏图片区域没有换图按钮。
- “设置 → 外观”提供樱花日常、星空放映室、夏日汽水三套主题，自定义强调色、字号和背景图片，支持亮度、柔化、面板不透明度与装饰开关。主窗口、应用内弹窗和悬浮窗即时换肤，点击“应用外观”后保存。
- 按年份和季度分页读取 Bangumi 番剧目录，封面分批后台加载；网络失败时使用已有本地缓存。
- 追更作品并匹配 AniList 日程，可手动选择候选或覆盖播出时间。
- “下一集”选取尚未播出的有效日程中最早的一集；过期手动时间不会显示为下一集，需要修改或清除覆盖时间。
- 本季番剧和我的追更显示每周播出星期；优先使用已获取的实际日程，只有首播日期时标注为推算，无可用信息时显示“未获取”。
- Windows 系统通知在播出时间到达后检查发送；取消提前分钟和单作品提醒设置，保留全局系统通知、悬浮窗开关、手动时间和延后提醒。
- 悬浮看板汇总昨天与今天的更新，可跨屏拖动并固定到指定屏幕，贴边隐藏后通过鼠标边缘感应或托盘菜单展开。
- 每部作品保存多个 HTTP/HTTPS 播放地址并指定默认项。
- 已看仓库支持编辑看完日期与感想、Bangumi 搜索添加和完全手动添加。
- 追更和仓库分别导出 `.anibackup`，包含清单、SHA-256 校验与封面；导入前自动创建快照并合并重复记录。

旧备份中的提前分钟和单作品提醒开关字段仅为兼容保留，不参与当前版本的提醒判断。AniDesk 不提供或抓取播放资源，也不会同步 Bangumi/AniList 账号收藏。

## 构建单文件 exe

完成上述开发环境安装后执行：

```powershell
cd anidesk_py
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm AniDesk.spec
```

产物为 `anidesk_py/dist/AniDesk-v0.2.0.exe`。该文件可单独分发，用户数据由首次运行时创建的 `data/` 保存。构建脚本从源码版本读取 EXE 文件名；以后升级版本时文件名同步变化。

## 保留的 Tauri 参考实现

`src/` 和 `src-tauri/` 保留的是 **v0.1.0 旧实现**，用于行为及 `.anibackup v1` 兼容参照，不包含当前 Python 主版本的更新。其数据目录和安装包构建方式与当前主版本不同。

旧实现需要 Node.js 20+、pnpm、Rust stable、Microsoft C++ Build Tools（Desktop development with C++）和 WebView2：

```powershell
pnpm install
pnpm test
pnpm tauri dev
```

`pnpm dev` 仅提供浏览器预览，使用 `localStorage`，外部 API 访问也受浏览器跨域策略限制。`pnpm tauri build` 构建的是旧版 Tauri 安装包，不是当前 Python 版的单文件 exe。
