# 本项目中的 STS2MCP

此目录保存 [Gennadiyev/STS2MCP](https://github.com/Gennadiyev/STS2MCP) 的本地源码快照，包含本项目的修改；原项目说明和构建方法见 [README.md](README.md)。此目录仍按原项目的 [MIT License](LICENSE) 发布，不受仓库根目录的 Apache-2.0 许可证替代。当前双模型控制器需要 Mod 状态中的永久牌组 `player.deck`。

编译需要 .NET 9 SDK 和本机《杀戮尖塔 2》的程序集。退出游戏后，在此目录运行：

```powershell
./build.ps1 -GameDir '<游戏安装目录>'
```

按 [原项目安装说明](README.md)把 `out/STS2_MCP/STS2_MCP.dll` 与 `mod_manifest.json` 安装到游戏的 `mods` 目录，后者需命名为 `STS2_MCP.json`。重新启动游戏后再检查 Mod 的 HTTP 接口是否提供 `player.deck`。`out/`、`bin/`、`obj/` 和本机 `../../outputs/hybrid/mod/` 中的 DLL 均为构建产物，不纳入公开仓库。源码修改后需重新编译并安装，单纯修改此目录不会改变游戏中的 Mod。
