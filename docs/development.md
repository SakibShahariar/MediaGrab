# Development Setup

These instructions target Fedora with GNOME. MediaGrab currently contains an initial GTK4/libadwaita UI shell; actual downloads are not implemented yet.

## Install system dependencies

```fish
sudo dnf install python3 python3-gobject gtk4 libadwaita
```

GTK introspection typelibs are supplied by the Fedora packages above. If the app reports that Gtk or Adw namespaces are unavailable, check that the matching system packages are installed.

## Run from the repository root

```fish
python3 -m venv --system-site-packages .venv
source .venv/bin/activate.fish
python -m pip install --editable .
mediagrab
```

If the environment does not expose the system PyGObject bindings inside the virtual environment, run the app with Fedora's system Python instead:

```fish
python3 -m app.mediagrab.main
```

## Current limitations

- The queue is in-memory and is lost when the app exits.
- Adding a URL only creates a placeholder queue row.
- No network requests or file downloads are performed.
- Browser extension and native messaging integration are not implemented.
