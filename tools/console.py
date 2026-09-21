"""Terminal output, shared by dev.py and the rest of the package.

Colours match what the old shell scripts printed, so the output of a build is
still recognisable.
"""

import sys

_CYAN, _GREEN, _YELLOW, _RED, _RESET = (
    "\033[1;36m", "\033[1;32m", "\033[1;33m", "\033[1;31m", "\033[0m",
)


class Failure(Exception):
    """A problem the user has to fix. dev.py reports it and exits non-zero.

    Modules raise this instead of calling sys.exit, so the watch loop can
    decide for itself whether a failure ends the session or just the rebuild.
    """


def say(message):
    print(f"{_CYAN}==>{_RESET} {message}", flush=True)


def ok(message):
    print(f"{_GREEN}  ok{_RESET} {message}", flush=True)


def warn(message):
    print(f"{_YELLOW}  !!{_RESET} {message}", file=sys.stderr, flush=True)


def error(message):
    print(f"{_RED}error:{_RESET} {message}", file=sys.stderr, flush=True)


def detail(message):
    print(f"    {message}", flush=True)
