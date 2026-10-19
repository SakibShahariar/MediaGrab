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

- Unfinished download URLs are saved to `$XDG_STATE_HOME/mediagrab/queue.json`, or `~/.local/state/mediagrab/queue.json` when `XDG_STATE_HOME` is not set.
- On restart, saved unfinished items are restored as **Interrupted**. They are not restarted automatically; use the retry button to resume or retry them.
- Queue persistence stores the full download URL so a queued item can be retried. If a URL contains signed query parameters or embedded credentials, those values may be written to the per-user queue file; avoid sharing that file and remove sensitive entries when no longer needed. Browser cookies and authorization headers are not currently collected. Partial transfer data remains in `~/Downloads` as `.part` files.
- Completed items are not persisted as history; their queue records are removed.
- At most three downloads run at once; additional downloads wait in the queue.
- Files are saved to `~/Downloads`; the destination is not configurable yet.
- Existing completed filenames are not overwritten.
- Interrupted downloads can resume if the server supports HTTP byte ranges. If the server ignores the range request, MediaGrab restarts the partial from byte zero.
- Cancellation is cooperative and may wait for the current network read to return or time out.
- Browser extension and native messaging integration are not implemented.
