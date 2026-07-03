# 多平台安装包策略

这份文档回答：如果扣舷要做成类似 MySkills 那样的跨平台发布，Windows、macOS、Linux 的安装包应该怎么做。

## 当前判断

扣舷当前是 Windows-first 项目，不建议立刻承诺 macOS / Linux 正式版。

原因不是 UI 不能跨平台，而是记录能力依赖系统权限：

- Windows：当前已经能记录键盘响应、鼠标响应和前台应用停留。
- macOS：需要 Accessibility / Input Monitoring 权限，分发必须签名和公证。
- Linux：桌面环境差异很大，Wayland 对全局输入监听限制更严格，X11 与 Wayland 行为不同。

因此安装包分两层推进：

1. **近期稳定线**：继续做好 Windows 安装器和便携包。
2. **跨平台线**：若要真正做到 macOS / Linux，优先迁移到 Tauri 2，再逐个平台实现本地记录后端。

## 推荐路线

### 路线 A：近期继续当前 Python / pywebview 方案

适合 `v1.7.x` 到 `v1.9`：

| 平台 | 发布物 | 做法 | 状态 |
| --- | --- | --- | --- |
| Windows | `.exe` 安装器 | PyInstaller + Inno Setup | 当前主线 |
| Windows | `.zip` 便携包 | PyInstaller onedir 后压缩 | 当前主线 |
| macOS | 暂不发布 | 先验证权限、签名、公证和输入记录能力 | 不承诺 |
| Linux | 暂不发布 | 先验证 X11 / Wayland 行为 | 不承诺 |

这条路线成本最低，但跨平台会越来越吃力。

### 路线 B：对齐 MySkills 的跨平台发布方式

适合进入 `v2.0` 方向评审后：

| 平台 | 推荐发布物 | 技术路线 |
| --- | --- | --- |
| macOS | 通用 `.dmg`，必要时同时提供 `.app` | Tauri 2 + Developer ID 签名 + Apple notarization + stapling |
| Windows | NSIS `-setup.exe`，可选 `.msi` | Tauri 2 bundler + Windows code signing + WebView2 检查 |
| Linux | `.AppImage`、`.deb`、`.rpm` | Tauri 2 bundler，在 Linux runner 上分别构建 |

这条路线更接近 MySkills：统一 Web 控制面，本地系统能力下沉到 Rust 后端，通过 GitHub Actions 分平台构建和发布。

## Windows

当前已经有两种包：

- `interaction-rhythm-setup-v版本号.exe`：普通用户优先使用，文件名暂时沿用旧更新链路。
- `interaction-rhythm.zip`：GitHub 更新包，适合稳定分发。
- `扣舷.zip`：中文朋友测试包。

近期继续使用：

```powershell
.\build.ps1
.\build-installer.ps1
```

发布前检查：

- `dist/releases/扣舷.zip` 和 `dist/releases/interaction-rhythm.zip` 不含数据库、日志、缓存和截图。
- `dist/releases/update.json` 的 `latest`、`sha256`、`size` 和下载地址正确。
- 安装器能创建开始菜单、桌面快捷方式和卸载入口。
- 旧版本应用内检查更新能发现新版。
- 升级后 `tracker.db`、设置和图标缓存保留。

后续如果迁移 Tauri，Windows 推荐用 NSIS `-setup.exe` 作为主包，`.msi` 作为企业/管理环境可选包。Tauri 官方说明 Windows 可发 `.msi` 或 NSIS setup exe；`.msi` 需要 Windows/WiX 环境，NSIS 跨平台构建也有 caveat，所以正式发布仍建议用 Windows runner 构建。

签名：

- 个人早期可以不签名，但会遇到 SmartScreen 提醒。
- 正式公开分发应准备 Windows code signing 证书。
- 不要为了绕过 SmartScreen 单独追 EV 证书。微软当前说明里，EV 证书已经不再自动带来 SmartScreen 信誉；非商店分发更推荐评估 Microsoft Trusted Signing / Artifact Signing，信誉仍会随下载量和行为逐步积累。

## macOS

macOS 不应直接复用 Windows 的“便携 zip”心智。普通用户应该拿到：

- `InteractionRhythm.dmg`
- 里面包含签名后的 `.app`
- 下载后双击打开，不要求用户执行终端绕过命令

正式发布要求：

- Apple Developer Program。
- Developer ID Application 证书。
- Hardened Runtime。
- 必要 entitlements。
- Notarization。
- Staple notarization ticket。

关键验证：

- 首次启动能清楚引导用户打开 Accessibility / Input Monitoring 权限。
- 没有权限时界面能解释“哪些记录不可用”，而不是静默失败。
- 签名和公证后的 `.dmg` 在干净 macOS 机器上双击可打开。

## Linux

Linux 推荐先做技术预览，不做强承诺。

推荐发布物：

- `.AppImage`：最适合试用，单文件分发。
- `.deb`：Debian / Ubuntu 用户。
- `.rpm`：Fedora / openSUSE / RHEL 系用户。

关键风险：

- X11 可以做更多全局监听。
- Wayland 对全局输入监听限制更强，不同 compositor 行为差异明显。
- 应用时长和前台窗口识别可能要分桌面环境适配。

发布策略：

- 先标注为 preview。
- 明确说明 X11 / Wayland 支持范围。
- UI 先能运行；记录能力按平台能力降级。

## 自动更新

当前 Windows 使用自定义 `update.json`：

```text
latest
download_url
sha256
size
notes
```

如果迁移到 Tauri，建议切到 Tauri updater 的 `latest.json` 结构。它支持静态 JSON 文件作为更新源，GitHub Release 可以承载这个文件。每个平台条目需要 URL 和 signature。

跨平台更新基本规则：

- 每个平台构建自己的更新包。
- 更新包必须签名。
- 客户端内置 public key。
- CI 使用 secret 保存 private signing key。
- 发布失败时不要更新 latest manifest。

## GitHub Actions 结构

建议未来拆成三个 runner：

```text
windows-latest -> NSIS setup exe / optional MSI / updater artifact
macos-latest   -> universal dmg / notarization / stapling / updater artifact
ubuntu-latest  -> AppImage / deb / rpm / updater artifact
```

发布流程：

1. bump 版本号。
2. 三个平台分别构建。
3. 运行 smoke test。
4. 签名 / 公证 / 生成 updater signature。
5. 上传 Release assets。
6. 最后生成并上传 `latest.json` 或当前格式的 `update.json`。

## 最小决策

近期建议：

- 继续把 Windows 做稳：安装器、便携包、更新、备份和预检。
- README 只写 Windows 正式安装，不提前承诺 macOS / Linux。
- `v2.0` 再决定是否迁移 Tauri，做真正跨平台。

如果要对外写一句话：

> 扣舷当前提供 Windows 安装器和便携包。macOS / Linux 会等记录权限、签名、公证和 Wayland 支持验证清楚后，再进入跨平台预览。
