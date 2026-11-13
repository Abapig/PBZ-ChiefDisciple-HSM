"""Dependency-free stdio MCP bridge to the Python plugin bundled with UE 5.8.

Uses newline-delimited JSON-RPC on stdin/stdout. Unreal discovery and command
traffic stays on loopback and is restricted to the configured project directory.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import time


TOOLS = [
    {
        "name": "unreal_status",
        "description": "Discover the configured Unreal project and verify a live editor connection.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "unreal_python",
        "description": "Execute Python in the configured Unreal Editor. Supports unreal.BlueprintEditorLibrary and native graph/pin APIs. Changes affect real editor assets; compile and save explicitly. Use unreal_status first.",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python source executed on the editor thread. Print results for inspection."}},
            "required": ["code"], "additionalProperties": False,
        },
    },
    {
        "name": "unreal_run_script",
        "description": "Execute a UTF-8 Python script from within the configured project in the live Unreal Editor. May modify assets.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute path or project-relative script path."}},
            "required": ["path"], "additionalProperties": False,
        },
    },
]


class UnrealBridge:
    def __init__(self, engine: Path, project: Path):
        self.project = project.resolve()
        self.engine = engine.resolve()
        sys.path.insert(0, str(self.engine / "Plugins/Experimental/PythonScriptPlugin/Content/Python"))
        import remote_execution
        self.module = remote_execution

    @contextlib.contextmanager
    def connection(self):
        config = self.module.RemoteExecutionConfig()
        config.multicast_bind_address = "127.0.0.1"
        config.multicast_ttl = 0
        # Each MCP process uses its own command port.
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        config.command_endpoint = ("127.0.0.1", port)
        remote = self.module.RemoteExecution(config)
        remote.start()
        try:
            deadline = time.monotonic() + 5
            match = None
            while time.monotonic() < deadline:
                for node in remote.remote_nodes:
                    root = node.get("project_root")
                    if root and os.path.normcase(str(Path(root).resolve())) == os.path.normcase(str(self.project)):
                        match = node
                        break
                if match:
                    break
                time.sleep(0.1)
            if match is None:
                raise RuntimeError(
                    "No remote Python editor found for this project. In Unreal, run "
                    "Content/Python/init_unreal.py via Tools > Execute Python Script, "
                    "or reopen the project so its startup script runs."
                )
            remote.open_command_connection(match["node_id"])
            yield remote, match
        finally:
            remote.stop()

    def call(self, name: str, arguments: dict):
        if name == "unreal_status":
            code = "import unreal, json; print(json.dumps({'engine_version': unreal.SystemLibrary.get_engine_version(), 'project_dir': unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), 'blueprint_editor_library': hasattr(unreal, 'BlueprintEditorLibrary'), 'blueprint_pin_library': hasattr(unreal, 'BlueprintGraphPinLibrary'), 'state_tree_editor_data': hasattr(unreal, 'StateTreeEditorData')}, ensure_ascii=True))"
        elif name == "unreal_python":
            code = arguments["code"]
            if not isinstance(code, str) or not code.strip():
                raise ValueError("code must be a non-empty string")
        elif name == "unreal_run_script":
            script = Path(arguments["path"])
            if not script.is_absolute():
                script = self.project / script
            script = script.resolve(strict=True)
            if not script.is_relative_to(self.project) or script.suffix.lower() != ".py":
                raise ValueError("script must be a .py file inside the configured project")
            code = "import runpy; runpy.run_path(" + repr(str(script)) + ", run_name='__main__')"
        else:
            raise ValueError("Unknown tool: " + name)
        with self.connection() as (remote, node):
            result = remote.run_command(code, unattended=True, raise_on_failure=False)
            result.pop("command", None)
            return {"editor": node, **result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    bridge = UnrealBridge(args.engine, args.project)
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("JSON-RPC request must be an object")
            if "id" not in request:
                continue
            method = request.get("method")
            params = request.get("params", {})
            if method == "initialize":
                supported = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
                version = params.get("protocolVersion")
                result = {
                    "protocolVersion": version if version in supported else "2025-11-25",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "unreal-project-bridge", "version": "1.0.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                try:
                    value = bridge.call(params["name"], params.get("arguments", {}))
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=True)}], "isError": not value.get("success", False)}
                except Exception as error:
                    result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
            else:
                print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "Method not found"}}), flush=True)
                continue
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None, "error": {"code": -32603, "message": str(error)}}
        print(json.dumps(response, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
