"""Versioned public D-Bus API for MediaGrab queue automation.

The API intentionally delegates to the application's shared external-command
handler so D-Bus callers receive the same validation and state checks as CLI
callers. Queue URLs returned by List are already redacted by the UI model.
"""

from __future__ import annotations

BUS_NAME = "io.github.SakibShahariar.MediaGrab"
OBJECT_PATH = "/io/github/SakibShahariar/MediaGrab"
INTERFACE_NAME = "io.github.SakibShahariar.MediaGrab1"

INTROSPECTION_XML = """<node>
  <interface name="io.github.SakibShahariar.MediaGrab1">
    <method name="AddUrl">
      <arg name="url" type="s" direction="in"/>
      <arg name="result" type="s" direction="out"/>
    </method>
    <method name="AddCandidate">
      <arg name="url" type="s" direction="in"/>
      <arg name="result" type="s" direction="out"/>
    </method>
    <method name="List">
      <arg name="result_json" type="s" direction="out"/>
    </method>
    <method name="Status">
      <arg name="result_json" type="s" direction="out"/>
    </method>
    <method name="Pause">
      <arg name="queue_id" type="u" direction="in"/>
      <arg name="result" type="s" direction="out"/>
    </method>
    <method name="Resume">
      <arg name="queue_id" type="u" direction="in"/>
      <arg name="result" type="s" direction="out"/>
    </method>
    <method name="Retry">
      <arg name="queue_id" type="u" direction="in"/>
      <arg name="result" type="s" direction="out"/>
    </method>
    <method name="Cancel">
      <arg name="queue_id" type="u" direction="in"/>
      <arg name="result" type="s" direction="out"/>
    </method>
  </interface>
</node>
"""

_METHOD_ACTIONS = {
    "AddUrl": "add-url",
    "AddCandidate": "add-candidate",
    "List": "list",
    "Status": "status",
    "Pause": "pause",
    "Resume": "resume",
    "Retry": "retry",
    "Cancel": "cancel",
}


def _method_call(_connection, _sender, _path, _interface, method_name, parameters, invocation, application):
    action = _METHOD_ACTIONS.get(method_name)
    if action is None:
        invocation.return_dbus_error(
            f"{INTERFACE_NAME}.Error.UnknownMethod",
            f"Unsupported MediaGrab method: {method_name}",
        )
        return
    argument = None
    if action in {"add-url", "add-candidate"}:
        argument = parameters.get_child_value(0).get_string()
    elif action in {"pause", "resume", "retry", "cancel"}:
        argument = str(parameters.get_child_value(0).get_uint32())
    try:
        result = application._execute_external_command(action, argument)
    except ValueError as exc:
        invocation.return_dbus_error(f"{INTERFACE_NAME}.Error.InvalidArgument", str(exc))
    except LookupError as exc:
        invocation.return_dbus_error(f"{INTERFACE_NAME}.Error.NotFound", str(exc))
    except RuntimeError as exc:
        invocation.return_dbus_error(f"{INTERFACE_NAME}.Error.InvalidState", str(exc))
    else:
        invocation.return_value(application._dbus_glib.Variant("(s)", (result,)))


def register_dbus_api(application, Gio, GLib) -> None:
    """Export the versioned API on the application's single-instance bus name."""
    if getattr(application, "_dbus_registration_id", 0):
        return
    connection = application.get_dbus_connection()
    if connection is None:
        raise RuntimeError("The application has no session-bus connection.")
    node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
    application._dbus_glib = GLib
    application._dbus_registration_id = connection.register_object(
        OBJECT_PATH,
        node.interfaces[0],
        lambda *args: _method_call(*args, application),
        None,
        None,
    )
