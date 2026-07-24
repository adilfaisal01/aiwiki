"""Migration runner entry point.

Allows running database migrations via `python -m migrations`.
"""

from migrations.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
