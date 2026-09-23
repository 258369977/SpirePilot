# 发布与下载

在项目根目录运行 `./build.ps1`。从 Python.org 下载 [Python 3.13.15 Windows x64 embeddable ZIP](https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip)，放到 `work/python-embed/python-3.13.15-embed-amd64.zip`；打包脚本会核对 SHA-256 `d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf`。然后运行 `./scripts/package_release.ps1 -Version v0.1.2`。脚本在 `work/release/v0.1.2/` 中生成：

- `SpirePilot-v0.1.2-win-x64.zip`：自包含 WinUI 3 应用、同级 Python 控制器及便携 Python 运行时。
- `STS2MCP-SpirePilot-v0.1.2.zip`：改版 Mod DLL、游戏 Mod 清单和原项目 MIT 许可证。
- `SHA256SUMS.txt`：两个 ZIP 的 SHA-256 校验值。

公开发布前运行 `python scripts/check_public_files.py`、`./test.ps1` 和 `git diff --cached --check`，核对暂存文件、两个 ZIP 内容和哈希。源码仓库排除 API 密钥、本机配置、对局日志、经验数据库、游戏文件和构建缓存；发布 ZIP 也不包含这些本机数据。应用包需保留 `SpirePilotApp/` 与 `hybrid/` 同级，Mod 包中的 DLL 与 JSON 要复制到游戏 `mods/` 目录。发布包中的 Python 无需安装到系统。

以预览版发布到 GitHub Releases，并附上这三个文件。Mod 是使用本机游戏程序集编译的；每次游戏更新后要重新核对兼容性。发布说明应明确：目前通过了本机测试、构建和界面冒烟检查，尚未完成整局付费模型实战验证。不要将 Mod 描述为官方版本或保证兼容所有游戏版本。
