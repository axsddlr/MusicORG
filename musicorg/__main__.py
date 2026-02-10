"""Entry point for `python -m musicorg`."""

import sys


def main():
    from musicorg.app import run_app
    sys.exit(run_app())


if __name__ == "__main__":
    main()
