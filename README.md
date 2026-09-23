# Spire Pilot

Spire Pilot 是《杀戮尖塔 2》的实验性双模型自动游玩项目。规划模型选择路线、卡牌和资源策略；战斗模型处理局内动作。WinUI 3 桌面端管理设置与对局，Python 控制器通过本机 STS2MCP Mod 与游戏交互，并在对局后保存可追溯的跨局经验。

## 下载预览版

从 [GitHub Releases](https://github.com/258369977/SpirePilot/releases) 下载 Windows x64 应用包、改版 STS2MCP Mod 包。解压应用包后，保持 `SpirePilotApp/` 与 `hybrid/` 同级。退出游戏并将 Mod 包中的 `STS2_MCP.dll` 与 `STS2_MCP.json` 放进游戏的 `mods/` 目录，启动游戏，再运行 `SpirePilotApp/SpirePilot.exe`。Mod 依赖游戏版本，更新游戏后需重新检查兼容性。

## 从源码运行

需要 Windows x64、Python 3.10+、.NET 9 SDK、游戏本体及本仓库中的改版 STS2MCP Mod。编译 Mod 时还需要本机游戏程序集；仓库不包含游戏文件。先按 [Mod 构建说明](vendor/STS2MCP/LOCAL.md)安装改版 Mod，再在项目根目录运行：

```powershell
./test.ps1
./build.ps1
./outputs/SpirePilotApp/SpirePilot.exe
```

在应用的“模型与设置”中分别填写规划模型和战斗模型的提供商、接口、模型 ID 与 API 密钥，然后保存设置。首次启动会读取 [配置模板](outputs/hybrid/config.example.json)；保存后生成本机 `outputs/hybrid/config.json`。
应用发布目录 `outputs/SpirePilotApp` 与控制器目录 `outputs/hybrid` 需保持同级。Mod 必须提供 `player.deck`；原版 STS2MCP 的构建不一定满足此要求。

## 目录

```text
outputs/SpirePilot/       WinUI 3 桌面端源码
outputs/hybrid/           Python 控制器、测试和配置模板
vendor/STS2MCP/          改版 Mod 源码及其原始许可证
docs/                    架构说明
work/                    本机构建缓存和临时文件（不提交）
```

对局日志、跨局经验数据库、本机配置和已发布应用都由 `.gitignore` 排除。`./build.ps1` 运行控制器测试并发布桌面应用；GitHub Actions 对 Python 测试和 WinUI 编译执行检查。Mod 依赖游戏程序集，未纳入在线 CI 编译。

详细设计见 [控制器说明](outputs/hybrid/README.md)、[桌面端说明](outputs/SpirePilot/README.md)和[架构说明](docs/README.md)。首次推送参见 [发布步骤](docs/PUBLISHING.md)。本项目尚未以桌面版完成充分的整局实战验证，不能据此推断胜率或长期稳定性。

## 许可证

本项目代码按 [Apache License 2.0](LICENSE) 发布。`vendor/STS2MCP/` 保留原项目的 [MIT License](vendor/STS2MCP/LICENSE)；来源和归属见 [第三方声明](THIRD_PARTY_NOTICES.md)。本项目与游戏开发商无关联。
