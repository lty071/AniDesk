# AniDesk

AniDesk 是一款面向 Windows 10/11 的本地优先桌面追番工具。它使用 Bangumi 获取中文番剧资料，使用 AniList 补充未来集数的精确播出时间，并将个人追更、播放地址、看完日期和感想保存在本机 SQLite 数据库中。

## Python + PySide6 实现

当前主实现位于 `anidesk_py/`，使用 Python 3.13、PySide6 Widgets、httpx、sqlite3、pytest 与 PyInstaller。现有 Tauri 源码继续保留，用于行为和 `.anibackup v1` 兼容验证。

```powershell
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e .\anidesk_py
.\.venv\Scripts\python.exe -m pytest .\anidesk_py\tests
.\.venv\Scripts\python.exe -m anidesk
```

应用数据保存在 `%LOCALAPPDATA%\AniDesk`。PyInstaller onedir 构建命令与目录说明见 `anidesk_py/README.md`。

## 已实现功能

- 按年份和季度自动分页读取完整 Bangumi 番剧目录，封面分批后台加载，网络失败时读取本地缓存。
- 追更作品并自动高置信度匹配 AniList 日程，支持手动选择候选或覆盖时间。
- Windows 系统通知、汇总昨天与今天更新且可鼠标悬停展开的贴边悬浮看板、托盘驻留和可选开机自启。
- 每部作品保存多个 HTTP/HTTPS 播放地址并指定默认项。
- 已看仓库、可在仓库页直接编辑保存的看完日期与感想、Bangumi 搜索添加及完全手动添加。
- 追更和仓库分别导出 `.anibackup`，包含清单、SHA-256 校验与封面；导入前自动快照并合并重复记录。
- 预留 `CloudSyncProvider`，首版不申请或使用任何飞书权限。

## 保留的 Tauri 参考实现

旧实现需要 Node.js 20+、pnpm、Rust stable、Microsoft C++ Build Tools（Desktop development with C++）和 WebView2。其依赖目录可按锁文件重新生成，源码和配置仍保留在仓库中。

```powershell
pnpm install
pnpm test
pnpm tauri dev
```

仅运行浏览器预览时可使用 `pnpm dev`。预览模式使用 `localStorage` 代替 SQLite，且浏览器跨域策略可能阻止直接访问外部 API；完整功能请通过 Tauri 运行。

## 构建 Windows 安装包

```powershell
pnpm tauri build
```

产物位于 `src-tauri/target/release/bundle/nsis/`。当前配置生成当前用户安装的简体中文 NSIS 安装包，未包含代码签名和自动更新。

## 数据说明

- 桌面版数据库：系统应用数据目录中的 `anidesk.db`。
- 自动导入前快照：应用数据目录的 `backups/` 子目录。
- 关闭主窗口时应用继续驻留托盘；请从托盘菜单选择“退出”以彻底结束。
- AniDesk 不提供播放资源、不抓取视频网站，也不会同步 Bangumi/AniList 账号收藏。
