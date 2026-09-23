Spire Pilot v0.1.2 是 Windows x64 预览版。应用包现在包含官方 Python 3.13.15 可嵌入运行时，桌面端会自动使用 `hybrid/python/python.exe`。首次使用不再需要安装 Python 或填写 Python 路径；如果已有自定义路径，设置仍可覆盖。

- `SpirePilot-v0.1.2-win-x64.zip`：完整解压后保留 `SpirePilotApp/` 和 `hybrid/` 同级，运行 `SpirePilotApp/SpirePilot.exe`。
- `STS2MCP-SpirePilot-v0.1.2.zip`：关闭游戏，把 `STS2_MCP.dll` 和 `STS2_MCP.json` 复制到游戏的 `mods/` 目录，然后重新启动游戏。
- `SHA256SUMS.txt`：校验两个 ZIP。

仍需《杀戮尖塔 2》、兼容的 Mod 和两组有效模型 API 配置。Python 软件许可证包含在应用包的 `hybrid/python/LICENSE.txt` 中；应用包不含 API 密钥、对局日志或本机经验数据库。

已验证：59 个控制器测试在普通 Python 和发布包内置 Python 3.13.15 下通过；从 ZIP 解压后，内置 Python 可以运行控制器，WinUI 冒烟模式能自动选择它并创建四个页面。尚未完成桌面版一整局付费模型实战验证，也未在全新 Windows 11 设备上完成安装验证。
