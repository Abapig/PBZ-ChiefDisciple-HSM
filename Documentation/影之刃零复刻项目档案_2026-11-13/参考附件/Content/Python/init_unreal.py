"""Enable this project's local-only Python bridge for the Unreal MCP server."""
import unreal

# This settings class is reflected by UE but is not necessarily exported as a
# named Python type. Resolve the native UClass and use native property names.
settings_class = unreal.load_class(
    None, "/Script/PythonScriptPlugin.PythonScriptPluginSettings"
)
if settings_class is None:
    raise RuntimeError("Unreal MCP: PythonScriptPlugin settings class was not found.")
settings = unreal.get_default_object(settings_class)
settings.set_editor_property("RemoteExecutionMulticastBindAddress", "127.0.0.1")
settings.set_editor_property("RemoteExecutionMulticastTtl", 0)
settings.set_editor_property("bRemoteExecution", True)
if not settings.get_editor_property("bRemoteExecution"):
    raise RuntimeError("Unreal MCP: remote execution setting did not become enabled.")
unreal.log("Unreal MCP: local Python remote execution enabled (127.0.0.1).")
