"""Enable ``python -m epochix`` as an alias for the ``epochix`` console script.

Useful when the ``epochix`` entry-point script isn't on PATH (a common case
on Windows, where pip installs it under ``…\\Scripts``). The VS Code extension
falls back to ``python -m epochix`` for exactly this reason.
"""

from epochix.cli import main_entry

if __name__ == "__main__":
    main_entry()
