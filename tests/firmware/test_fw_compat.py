"""Keeps the firmware to the Python that CircuitPython runs.

The tests run the firmware on CPython, which would happily accept features
the Pico doesn't have. These checks catch the common ones before they reach
the device: no match statements, dataclasses, enums or type hints, and no
str methods CircuitPython leaves out.
"""

import ast
import io
import tokenize
from pathlib import Path

import pytest

FIRMWARE = Path(__file__).parents[2] / "firmware"
SOURCES = sorted(FIRMWARE.rglob("*.py"))

# Not in CircuitPython (or not worth their RAM on the Pico).
MISSING_MODULES = {
    "abc",
    "dataclasses",
    "enum",
    "functools",
    "pathlib",
    "re",
    "typing",
    "unicodedata",
}
MISSING_STR_METHODS = {"capitalize", "casefold", "isalnum", "removeprefix", "removesuffix", "title"}


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(FIRMWARE)))
def test_firmware_uses_circuitpython_python(path: Path):
    source = path.read_text("utf-8")
    tree = ast.parse(source)
    problems = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Match):
            problems.append(f"line {line}: match statement")
        elif isinstance(node, ast.NamedExpr):
            problems.append(f"line {line}: := (walrus)")
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            )
            for name in names:
                if name and name.split(".")[0] in MISSING_MODULES:
                    problems.append(f"line {line}: import {name}")
        elif isinstance(node, ast.arg | ast.AnnAssign) and node.annotation is not None:
            problems.append(f"line {line}: type annotation")
        elif isinstance(node, ast.FunctionDef) and node.returns is not None:
            problems.append(f"line {line}: return annotation")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in MISSING_STR_METHODS
        ):
            problems.append(f"line {line}: .{node.func.attr}()")
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NUMBER and "_" in token.string:
            problems.append(f"line {token.start[0]}: underscore in number {token.string}")
    assert not problems, f"{path.name}: " + "; ".join(problems)


def test_found_the_firmware():
    assert FIRMWARE / "code.py" in SOURCES
