Spire Pilot v0.1.0 是 Windows x64 预览版，提供 WinUI 3 桌面端、双模型 Python 控制器和改版 STS2MCP Mod。规划模型负责路线、抓牌和资源选择，战斗模型负责局内动作；两者分别配置提供商、模型和 API 密钥。对局日志与跨局经验保存在本机。

下载文件：

- `SpirePilot-v0.1.0-win-x64.zip`：解压后保留 `SpirePilotApp/` 与 `hybrid/` 同级；运行 `SpirePilotApp/SpirePilot.exe`。
- `STS2MCP-SpirePilot-v0.1.0.zip`：关闭游戏，将 `STS2_MCP.dll` 和 `STS2_MCP.json` 复制到游戏的 `mods/` 目录，再启动游戏。该 Mod 提供控制器要求的 `player.deck`。
- `SHA256SUMS.txt`：下载文件校验值。

另需在本机安装 Python 3.10+ 和《杀戮尖塔 2》。应用包自带 .NET 与 Windows App SDK 运行文件；API 密钥需要在应用内分别配置，不包含在下载包中。改版 Mod 采用原项目 MIT 许可证，项目其余代码采用 Apache-2.0。

已验证：59 个 Python 测试通过；Windows 应用构建成功；从发布 ZIP 解压后的程序在暗色、宽屏冒烟模式下识别到控制器，并创建四个页面。尚未完成桌面版一整局付费模型实战验证；Mod 与其他游戏版本的兼容性也未验证。
