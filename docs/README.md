# 项目结构

桌面应用、控制器和游戏 Mod 通过以下路径协作：

1. WinUI 3 桌面端（`outputs/SpirePilot`）通过 `desktop_bridge.py` 读取设置、启动或停止后台控制器、展示状态和历史。
2. Python 控制器（`outputs/hybrid/hybrid_player.py`）从本机 STS2MCP HTTP 接口读取当前局面，只提交游戏接口列出的合法动作。
3. 战略界面由规划模型选择路线、奖励和资源决策，并更新给战斗模型看的简短计划；战斗界面由战斗模型选择具体动作。
4. `role_memory.py` 将两种职责的工作记忆分开。规划模型在战斗后只接收结果交接；战斗模型读取当前战斗观测与相关历史案例。
5. `run_journal.py` 在每局的 SQLite 文件中记录观测、决策、动作及后续结果；`experience.py` 管理跨局规划经验和战斗案例。

`outputs/hybrid/runs`、`outputs/hybrid/experience`、`outputs/hybrid/config.json` 和桌面端发布目录均为本机数据或构建产物，已从 Git 排除。公开仓库只包含配置模板、源码、测试与文档。真实对局日志生成的分析材料也保留在本机 `work/research-notes`，不随仓库发布。
