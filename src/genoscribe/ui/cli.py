from __future__ import annotations

from genoscribe.app import main


def run_cli() -> None:
    """Entry point used by ui experiments; delegates to core app."""
    main()


__all__ = ["run_cli"]
