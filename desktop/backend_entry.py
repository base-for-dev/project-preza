"""Entry point of the frozen backend: the same `preza` command, inside one executable."""

from server.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
