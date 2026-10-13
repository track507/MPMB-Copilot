"""
Model-chosen grep patterns, matched in time bounded by the input

RE2 runs in time linear in the line length and cannot backtrack catastrophically
A pattern RE2 rejects (lookaround, backreference) runs on the regex package under a timeout, with the GIL released
"""

from collections.abc import Callable

import re2
import regex

LineSearch = Callable[[str, float], bool]

_RE2_OPTIONS = re2.Options()
_RE2_OPTIONS.log_errors = False


def compile_line_pattern(pattern: str) -> LineSearch | str:
    """
    A line search on the safest engine that accepts the pattern, or an [error] string

    The search takes the line and the seconds it may spend, and raises TimeoutError on the fallback engine
    """
    try:
        linear = re2.compile(pattern, _RE2_OPTIONS)
    except re2.error:
        pass
    else:
        return lambda line, _timeout: linear.search(line) is not None

    try:
        backtracking = regex.compile(pattern)
    except regex.error as e:
        return f"[error] invalid regex: {e}"
    return lambda line, timeout: backtracking.search(line, concurrent=True, timeout=timeout) is not None
