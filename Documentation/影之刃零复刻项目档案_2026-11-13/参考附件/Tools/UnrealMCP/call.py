"""Exercise the actual MCP stdio transport, including initialize and tools/call."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", choices=["unreal_status", "unreal_python", "unreal_run_script", "list"])
    parser.add_argument("--code")
    parser.add_argument("--path")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    engine = Path(sys.executable).resolve().parents[4]
    command = [sys.executable, "-B", "-u", str(Path(__file__).with_name("server.py")), "--engine", str(engine), "--project", str(project)]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None, text=True, encoding="utf-8") as process:
        def rpc(request):
            process.stdin.write(json.dumps(request, ensure_ascii=True) + "\n")
            process.stdin.flush()
            return json.loads(process.stdout.readline())
        initialized = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "unreal-bridge-check", "version": "1"}}})
        if "error" in initialized:
            raise RuntimeError(initialized)
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        process.stdin.flush()
        if args.tool == "list":
            request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        else:
            arguments = {}
            if args.code:
                arguments["code"] = args.code
            if args.path:
                arguments["path"] = args.path
            request = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": args.tool, "arguments": arguments}}
        response = rpc(request)
        process.stdin.close()
        process.wait(timeout=10)
    formatted = json.dumps(response, ensure_ascii=True, indent=2)
    print(formatted)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted + "\n", encoding="utf-8")
    if "error" in response or response.get("result", {}).get("isError"):
        sys.exit(1)


if __name__ == "__main__":
    main()
