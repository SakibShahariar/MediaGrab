# Development Setup

These instructions target Fedora with GNOME. MediaGrab currently has a GTK4/libadwaita download queue and a basic HTTP(S) download core. Browser media capture is not implemented yet.

## Install system dependencies

```fish
sudo dnf install python3 python3-gobject gtk4 libadwaita
```

## Set up a development environment

From the repository root:

```fish
python3 -m venv --system-site-packages .venv
source .venv/bin/activate.fish
python -m pip install --editable ".[test]"
```

The `--system-site-packages` option lets the virtual environment see Fedora's PyGObject bindings. If GTK namespaces are unavailable, run the app with Fedora's system Python after installing the system packages.

## Run the app

```fish
mediagrab
```

Or, without installing the console entry point:

```fish
python -m mediagrab.main
```

## Run tests

```fish
python -m pytest -v
```

Tests use a local HTTP server and do not need an external download URL or internet access.

## Current limitations

- The queue is in-memory and is lost when the app exits.
- At most three downloads run at once; additional downloads wait in the in-memory queue.
- Files are saved to `~/Downloads`; the destination is not configurable yet.
- Existing completed filenames are not overwritten.
- Interrupted downloads keep a `.part` file. A new task can resume it if the server correctly supports HTTP byte ranges. If the server ignores the range request, MediaGrab restarts the partial from byte zero.
- Cancellation is cooperative and may wait for the current network read to return or time out.
- Failed or cancelled rows expose a retry/resume action; the download core attempts to continue from an existing `.part` file when the server supports byte ranges.
- Browser extension and native messaging integration are not implemented.
