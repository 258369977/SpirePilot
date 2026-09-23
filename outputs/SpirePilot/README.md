# Spire Pilot

原生 WinUI 3 桌面应用，连接旁边的 `hybrid` Python 控制器。规划模型处理路线、抓牌与构筑计划，战斗模型处理局内动作；完整对局结束后自动复盘，经验写入 SQLite 并供后续对局检索。

界面会读取 Windows 的应用主题，并在系统切换浅色或深色主题时同步更新页面、卡片、控件和标题栏，无需重启应用。

## 启动

直接打开 `../SpirePilotApp/SpirePilot.exe`。发布目录已包含 .NET、Windows App SDK 和 Python 3.13.15 运行文件，请保留整个目录，不要只复制 EXE。应用会自动选择同级 `hybrid/python/python.exe`；只有从源码运行且没有便携运行时的情况下才需要系统 Python 3.10+。控制器仅使用 Python 标准库。

目录结构保持为：

```
outputs/
  SpirePilotApp/SpirePilot.exe
  hybrid/desktop_bridge.py
  hybrid/config.example.json
  hybrid/python/python.exe  # 发布包内置，自动选择
  hybrid/config.json  # 首次保存设置后在本机生成
```

1. 从 Steam 打开已装 STS2MCP 的游戏。Mod 必须提供完整永久牌组 `player.deck`。
2. 在“模型与设置”为规划模型和战斗模型分别填写对应提供商的 API 密钥。模板分别使用 DeepSeek 和 TypeSafe API。勾选“保存到 Windows 凭据管理器”后点击保存，密钥会保存在当前 Windows 用户的凭据库中，不写入配置文件。
3. 点击“检查游戏连接”，然后“开始 / 接管当前对局”。运行计划、血量、层数和日志在控制台更新。
4. 关闭窗口后后台仍继续游玩。要停止请点击“停止自动游玩”；正在进行的模型请求返回后停止，不强行终止游戏。
5. 中断后在“历史与复盘”选择原记录并继续，游戏内应加载同一局。新一局使用控制台的开始按钮，避免混用旧计划。

长期规划和战斗各自配置提供商、模型、API 密钥、完整 API 地址及接口类型。规划模型另有思考强度选项，默认“低”，同时用于战略决策与局后复盘。预设提供商包括 OpenRouter、DeepSeek、自定义；模型 ID 必须与对应提供商匹配。选择 DeepSeek 时使用 JSON Object 聊天接口；当前 Jev 配置使用 TypeSafe 的 Decisions 接口。其他战斗模型可以选择 JSON Schema 或 JSON Object 聊天接口，服务端需支持相应格式。

启动、续局、补跑复盘前会保存当前界面的设置。规划与战斗密钥按职责和提供商地址分别存入 Windows 凭据管理器，通过 stdin 传给桥接程序，再临时放入对应子进程环境；配置、日志和命令行都不包含密钥。密钥框留空时优先读取匹配的 Windows 凭据，否则读取 `SPIRE_PLANNER_KEY` 或 `SPIRE_COMBAT_KEY`。取消勾选并保存会删除当前提供商地址的凭据，只使用本次输入或环境变量。补跑复盘只读取规划密钥。切换提供商或 API 主机时不会复用另一地址的密钥；切换回来可以继续使用原来保存的凭据。

## 页面

- 对局控制台：启动、停止、连接检查、当前计划与日志。
- 模型与设置：两组提供商、接口类型、模型 ID、密钥、跨局记忆开关、版本隔离标签、控制器路径和可选的 Python 路径覆盖。
- 历史与复盘：恢复记录、查看复盘、对已结束的对局补跑复盘。
- 跨局经验库：查看带来源与证据的经验。经验仍是模型提出的假设，不能视为已验证结论。

对局日志保存在 `hybrid/runs`，每局的完整关联事实位于 `run-memory.sqlite3`，工作记忆位于 `memory.json`。跨局记忆默认保存在 `hybrid/experience/lessons.sqlite3`：规划侧显示带证据的复盘假设，战斗侧显示控制器从战斗日志生成的结构化事实案例，二者分别检索。应用不包含 API 费用估算、累计或展示功能。详细控制器行为见 `../hybrid/README.md`。

## 构建与验证

源码使用 .NET 9、Windows App SDK 1.8，目标 Windows x64。在有 .NET 9 SDK 和对应 Windows 构建工具的 Windows 环境执行：

```powershell
./build.ps1
```

可传入 `-Dotnet '完整路径/dotnet.exe'` 和 `-NuGetConfig 'NuGet.Config路径'`。发布时会复制所需的 XAML 编译资源。

```powershell
python -m unittest discover -s ../hybrid -p 'test_*.py' -v
../SpirePilotApp/SpirePilot.exe --smoke-test
```

冒烟模式读取本地配置、状态、历史与经验库，依次创建四个页面，输出 `ui-smoke.json` 和 `ui-preview.png` 后退出。不会调用模型或发送游戏动作。异常记录在应用目录的日志文件中。

当前已验证本机编译、发布版启动、四页切换和后台读取，以及控制器与记忆测试。尚未通过这个桌面版完成一整局付费模型实战；这不能作为胜率或长期稳定性验证。
