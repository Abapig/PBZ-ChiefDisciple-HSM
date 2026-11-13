"""Create and verify a disposable diagnostic Blueprint through live editor APIs."""
import json
from pathlib import Path
import traceback
import unreal


def require(value, message):
    if not value:
        raise RuntimeError(message)
    return value


def describe(blueprint):
    library = unreal.BlueprintEditorLibrary
    graphs = []
    for graph in library.list_graphs(blueprint):
        editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
        nodes = []
        for node in editor.list_all_nodes():
            pins = []
            for pin in node.list_all_pins():
                pins.append({
                    "name": str(pin.get_pin_name()),
                    "direction": str(pin.get_pin_direction()),
                    "value": pin.get_pin_value(),
                    "connections": [
                        {"node": other.get_owning_node().get_name(), "pin": str(other.get_pin_name())}
                        for other in pin.list_connected_pins()
                    ],
                })
            position = node.get_node_pos()
            nodes.append({"name": node.get_name(), "title": node.get_node_title(), "class": node.get_class().get_name(), "position": [position.x, position.y], "pins": pins})
        graphs.append({"name": graph.get_name(), "nodes": nodes})
    return {"asset": blueprint.get_path_name(), "variables": list(library.list_member_variable_names(blueprint, False)), "graphs": graphs}


def run(report):
    library = unreal.BlueprintEditorLibrary
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    package, asset_name = asset_tools.create_unique_asset_name("/Game/MCPDiagnostics/BP_MCP_Probe", "")
    report["asset"] = package
    blueprint = require(library.create_blueprint_asset_with_parent(package, unreal.Actor), "Blueprint creation failed")
    report["create_blueprint"] = True

    editor = unreal.BlueprintGraphEditor.create_and_edit_function_graph(blueprint, "MCPProbe")
    float_type = library.get_basic_type_by_name("float")
    require(editor.add_member_variable("ProbeHealth", float_type, "100.0"), "Add member variable failed")
    library.set_blueprint_variable_instance_editable(blueprint, "ProbeHealth", True)
    library.set_blueprint_variable_category(blueprint, "ProbeHealth", "MCP Diagnostics")
    report["add_variable"] = True

    incoming = editor.add_graph_input_parameter("NewHealth", float_type)
    result_node = editor.add_graph_output_parameter("ResultHealth", float_type)
    setter = require(editor.add_set_member_variable_node("ProbeHealth"), "Create setter failed")
    getter = require(editor.add_get_member_variable_node("ProbeHealth"), "Create getter failed")
    setter.set_node_pos(unreal.IntPoint(260, 0))
    getter.set_node_pos(unreal.IntPoint(260, 220))
    result_node.set_node_pos(unreal.IntPoint(560, 0))
    require(editor.find_graph_entry_pin().try_create_connection(setter.find_execute_pin()), "Entry execution connection failed")
    require(incoming.try_create_connection(setter.find_input_pin("ProbeHealth")), "Input data connection failed")
    require(setter.find_then_pin().try_create_connection(result_node.find_execute_pin()), "Return execution connection failed")
    require(getter.find_result_pin().try_create_connection(result_node.find_input_pin("ResultHealth")), "Return data connection failed")
    report["add_nodes_and_connect_pins"] = True

    event_editor = unreal.BlueprintGraphEditor.get_graph_editor_by_name(blueprint, "EventGraph")
    begin_play = event_editor.find_event_node("ReceiveBeginPlay")
    if begin_play is None:
        begin_play = library.add_event_override(blueprint, "ReceiveBeginPlay", unreal.IntPoint(0, 0))
    printer = require(event_editor.add_call_function_node("/Script/Engine.KismetSystemLibrary.PrintString"), "Create PrintString node failed")
    printer.set_node_pos(unreal.IntPoint(320, 0))
    require(printer.find_input_pin("InString").set_pin_value("MCP Blueprint connection verified"), "Set pin literal failed")
    require(begin_play.find_then_pin().try_create_connection(printer.find_execute_pin()), "BeginPlay connection failed")
    report["set_pin_literal"] = True

    require(library.compile_blueprint(blueprint), "Blueprint compiler reported errors")
    report["compile"] = True
    default_object = unreal.get_default_object(blueprint.generated_class())
    returned = default_object.call_method("MCPProbe", (321.0,))
    health = default_object.get_editor_property("ProbeHealth")
    require(abs(float(returned) - 321.0) < 0.001 and abs(float(health) - 321.0) < 0.001, "Generated Blueprint function did not execute correctly")
    report["execute_generated_function"] = {"input": 321.0, "returned": returned, "member_value": health}
    default_object.set_editor_property("ProbeHealth", 100.0)
    require(unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False), "Save Blueprint asset failed")
    report["saved"] = True
    readback = require(unreal.load_asset(package), "Read back Blueprint failed")
    report["readback"] = describe(readback)
    original = unreal.load_asset("/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter")
    if original:
        report["existing_blueprint_read_only"] = {"asset": original.get_path_name(), "graphs": [g.get_name() for g in library.list_graphs(original)], "variables": list(library.list_member_variable_names(original, False))}
    report["state_tree_api_available"] = {
        name: hasattr(unreal, name) for name in ["StateTree", "StateTreeFactory", "StateTreeEditorData", "StateTreeState", "StateTreeTaskBlueprintBase", "StateTreeConditionBlueprintBase"]
    }
    report["success"] = True


if __name__ == "__main__":
    report = {"success": False}
    try:
        run(report)
    except Exception:
        report["error"] = traceback.format_exc()
        raise
    finally:
        destination = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())) / "UnrealMCP/blueprint_probe.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "readback"}, ensure_ascii=True))
