from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from mediagrab import dbus_api


class FakeValue:
    def __init__(self, value):
        self.value = value

    def get_string(self):
        return self.value

    def get_uint32(self):
        return self.value


class FakeParameters:
    def __init__(self, value=None):
        self.value = value

    def get_child_value(self, _index):
        return FakeValue(self.value)


class FakeVariant:
    def __init__(self, signature, values):
        self.signature = signature
        self.values = values


class FakeGLib:
    Variant = FakeVariant


class FakeInvocation:
    def __init__(self):
        self.value = None
        self.error = None

    def return_value(self, value):
        self.value = value

    def return_dbus_error(self, name, message):
        self.error = (name, message)


class FakeApplication:
    _dbus_glib = FakeGLib

    def __init__(self, result="ok", error=None):
        self.result = result
        self.error = error
        self.calls = []

    def _execute_external_command(self, action, argument):
        self.calls.append((action, argument))
        if self.error:
            raise self.error
        return self.result


def invoke(method, value=None, *, error=None):
    app = FakeApplication(error=error)
    invocation = FakeInvocation()
    dbus_api._method_call(
        None, ":1.10", dbus_api.OBJECT_PATH, dbus_api.INTERFACE_NAME,
        method, FakeParameters(value), invocation, app,
    )
    return app, invocation


def test_dbus_interface_is_versioned_and_declares_every_operation():
    root = ET.fromstring(dbus_api.INTROSPECTION_XML)
    interface = root.find("interface")
    assert interface is not None
    assert interface.attrib["name"] == "io.github.SakibShahariar.MediaGrab1"
    assert {item.attrib["name"] for item in interface.findall("method")} == {
        "AddUrl", "AddCandidate", "List", "Status", "Pause", "Resume", "Retry", "Cancel"
    }


@pytest.mark.parametrize(
    ("method", "value", "expected"),
    [
        ("AddUrl", "https://example.test/file.mp4", ("add-url", "https://example.test/file.mp4")),
        ("AddCandidate", "https://example.test/master.m3u8", ("add-candidate", "https://example.test/master.m3u8")),
        ("List", None, ("list", None)),
        ("Status", None, ("status", None)),
        ("Pause", 4, ("pause", "4")),
        ("Resume", 5, ("resume", "5")),
        ("Retry", 6, ("retry", "6")),
        ("Cancel", 7, ("cancel", "7")),
    ],
)
def test_dbus_methods_share_the_application_command_handler(method, value, expected):
    app, invocation = invoke(method, value)
    assert app.calls == [expected]
    assert invocation.error is None
    assert invocation.value.signature == "(s)"
    assert invocation.value.values == ("ok",)


@pytest.mark.parametrize(
    ("error", "suffix"),
    [
        (ValueError("invalid URL"), "InvalidArgument"),
        (LookupError("missing item"), "NotFound"),
        (RuntimeError("item is active"), "InvalidState"),
    ],
)
def test_dbus_errors_are_returned_as_actionable_named_errors(error, suffix):
    _app, invocation = invoke("Retry", 1, error=error)
    assert invocation.value is None
    assert invocation.error == (
        f"{dbus_api.INTERFACE_NAME}.Error.{suffix}", str(error)
    )


def test_unknown_method_is_rejected():
    app, invocation = invoke("Delete", 1)
    assert app.calls == []
    assert invocation.error == (
        f"{dbus_api.INTERFACE_NAME}.Error.UnknownMethod",
        "Unsupported MediaGrab method: Delete",
    )


def test_registration_exports_the_versioned_object_and_dispatches_methods():
    class FakeInterface:
        pass

    class FakeNodeInfo:
        interfaces = [FakeInterface()]

        @staticmethod
        def new_for_xml(xml):
            assert xml == dbus_api.INTROSPECTION_XML
            return FakeNodeInfo()

    class FakeConnection:
        def register_object(self, path, interface, callback, _get, _set):
            self.path = path
            self.interface = interface
            self.callback = callback
            return 73

    class FakeGio:
        DBusNodeInfo = FakeNodeInfo

    class RegisteringApplication(FakeApplication):
        def __init__(self):
            super().__init__(result='registered')
            self.connection = FakeConnection()

        def get_dbus_connection(self):
            return self.connection

    app = RegisteringApplication()
    dbus_api.register_dbus_api(app, FakeGio, FakeGLib)

    assert app.connection.path == dbus_api.OBJECT_PATH
    assert app.connection.interface is FakeNodeInfo.interfaces[0]
    assert app._dbus_registration_id == 73

    invocation = FakeInvocation()
    app.connection.callback(
        None, ":1.2", dbus_api.OBJECT_PATH, dbus_api.INTERFACE_NAME,
        "AddUrl", FakeParameters("https://example.test/file.mp4"), invocation,
    )
    assert app.calls == [("add-url", "https://example.test/file.mp4")]
    assert invocation.value.values == ("registered",)
