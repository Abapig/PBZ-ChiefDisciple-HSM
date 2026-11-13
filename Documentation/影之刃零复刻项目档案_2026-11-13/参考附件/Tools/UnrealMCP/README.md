# 本项目的 Unreal MCP

此服务使用 UE 5.8 自带 Python 解释器及 `remote_execution.py`，无需下载 Python 包或第三方 UE 插件。

连接链路：Codex → stdio MCP → 本机 Unreal Python → BlueprintEditorLibrary / BlueprintGraphEditor。

## 启动

Codex 全局 MCP 配置中的服务名为 `unreal_project`。服务由 MCP 客户端按需启动。

项目启动时，`Content/Python/init_unreal.py` 会开启仅限本机的远程 Python。对于已经打开的编辑器，在「工具 → 执行 Python 脚本」中手动执行该文件一次即可，不需要重启 UE。

首次注册服务后，如当前 Codex 聊天没有出现新工具，需重新加载 Codex 的 MCP 连接或重新打开 Codex。当前工作也可用下述命令通过真实 MCP stdio 协议验证。

## 工具

- `unreal_status`：匹配本项目的编辑器，读取引擎版本和 API 能力。
- `unreal_python`：在编辑器主线程执行 Python，可以读写蓝图；修改后应编译并保存。
- `unreal_run_script`：执行本项目内的 Python 脚本。

服务器限定匹配配置的项目路径，发现及命令连接均使用本机回环接口。编辑器不能停在阻塞主线程的模态窗口或断点上。

## 连接和蓝图验证

在项目目录中运行 PowerShell：

```powershell
& 'D:\Program Files\Unreal\UE_5.8\Engine\Binaries\ThirdParty\Python3\Win64\python.exe' -B '.\Tools\UnrealMCP\call.py' unreal_status
& 'D:\Program Files\Unreal\UE_5.8\Engine\Binaries\ThirdParty\Python3\Win64\python.exe' -B '.\Tools\UnrealMCP\call.py' unreal_run_script --path 'Tools/UnrealMCP/probe_blueprint.py'
```

验证会在 `/Game/MCPDiagnostics` 创建独立蓝图，不修改第三人称角色。重复执行使用新的唯一资产名。它创建变量和函数、放置节点、连接执行及数据引脚、设置引脚文字、编译，并实际调用生成的蓝图函数验证返回值，最后保存资产。

验证结果写入 `Saved/UnrealMCP/blueprint_probe.json`。只有报告的 `success` 为 `true` 才表示完整验证成功；StateTree API 是否存在不等于已经验证 StateTree 编辑或运行。

2026-11-11 已通过真实 MCP stdio 请求连接本项目正在运行的 UE 5.8.4 编辑器，完成上述验证。测试资产为 `/Game/MCPDiagnostics/BP_MCP_Probe`，生成函数输入 321 后，返回值及成员变量值均为 321，编译及保存成功。

启动脚本通过 `/Script/PythonScriptPlugin.PythonScriptPluginSettings` 加载原生类，再用原生属性名设置默认对象；本版本没有导出 `unreal.PythonScriptPluginSettings`，不能直接引用该 Python 类型名。

## 移除

使用 `codex mcp remove unreal_project` 移除 Codex 配置。删除本项目的 `Content/Python/init_unreal.py` 可停止下次启动自动启用远程 Python；当前运行的编辑器可在项目设置的 Python 页面关闭 Enable Remote Execution。
