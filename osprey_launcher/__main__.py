"""Starts Osprey Launcher. Used by `python -m osprey_launcher` and as the PyInstaller entry point."""

from osprey_launcher.app import main

raise SystemExit(main())
