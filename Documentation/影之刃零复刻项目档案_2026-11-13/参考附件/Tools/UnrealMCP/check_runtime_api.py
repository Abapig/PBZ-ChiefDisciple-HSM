"""Check native settings lookup and actual Python API exports inside UE."""
import json
from pathlib import Path
import runpy
import traceback
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
report = {"engine_version": unreal.SystemLibrary.get_engine_version()}
try:
    runpy.run_path(str(project / "Content/Python/init_unreal.py"))
    report["bootstrap_success"] = True
except Exception:
    report["bootstrap_success"] = False
    report["bootstrap_error"] = traceback.format_exc()
for name in ["BlueprintEditorLibrary", "BlueprintGraphEditor", "BlueprintGraphPinLibrary", "StateTree", "StateTreeEditorData", "StateTreeTaskBlueprintBase"]:
    obj = getattr(unreal, name, None)
    report[name] = {"available": obj is not None, "methods": [n for n in dir(obj) if not n.startswith("_")]} if obj else {"available": False}
destination = project / "Saved/UnrealMCP/runtime_api.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
unreal.log("UNREAL_MCP_RUNTIME_CHECK " + json.dumps(report, ensure_ascii=True))
