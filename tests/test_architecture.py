"""Enforce layer boundaries and installation independence as the project grows."""

import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import ip_scanner_helper

PACKAGE = Path(ip_scanner_helper.__file__).resolve().parent
PREFIX = "ip_scanner_helper"
ALLOWED = {
    "domain": {"domain"},
    "application": {"application", "domain"},
    "infrastructure": {"infrastructure", "application", "domain", "resources"},
    "presentation": {"presentation", "application", "domain", "resources"},
    "resources": {"resources"},
}


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise AssertionError(f"Use explicit package imports: {path}:{node.lineno}")
            if node.module:
                yield node.module


class ArchitectureTests(unittest.TestCase):
    def test_dependencies_follow_layer_boundaries(self):
        for path in PACKAGE.rglob("*.py"):
            layer = path.relative_to(PACKAGE).parts[0]
            if layer not in ALLOWED:
                continue
            for dependency in imports(path):
                with self.subTest(path=str(path.relative_to(PACKAGE)), dependency=dependency):
                    top = dependency.split(".")[0]
                    if dependency.startswith(PREFIX + "."):
                        self.assertIn(dependency.split(".")[1], ALLOWED[layer])
                    elif top in {"PySide6", "shiboken6"}:
                        self.assertEqual(layer, "presentation", "Qt belongs in presentation")
                    elif layer in {"domain", "application", "resources"}:
                        self.assertIn(top, sys.stdlib_module_names, "Inner layers use the standard library")
                    self.assertNotIn(top, {"core", "ui", "tkinter"})

    def test_internal_imports_have_no_cycles(self):
        paths = {}
        for path in PACKAGE.rglob("*.py"):
            parts = list(path.relative_to(PACKAGE).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            paths[".".join([PREFIX, *parts])] = path
        graph = {module: {name for name in imports(path) if name in paths} for module, path in paths.items()}
        visited, visiting = set(), []

        def visit(module):
            self.assertNotIn(module, visiting, "Dependency cycle: " + " -> ".join([*visiting, module]))
            if module in visited:
                return
            visiting.append(module)
            for dependency in graph[module]:
                visit(dependency)
            visiting.pop()
            visited.add(module)

        for module in graph:
            visit(module)

    def test_application_import_needs_neither_qt_nor_network_implementations(self):
        code = """
import sys
from ip_scanner_helper.application.scanner import scan_device
from ip_scanner_helper.application.scan_service import ScanService
assert not any(name.startswith(('PySide6', 'ip_scanner_helper.infrastructure')) for name in sys.modules)
"""
        result = subprocess.run([sys.executable, "-I", "-X", "utf8", "-B", "-c", code],
                                capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installed_cli_works_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-I", "-X", "utf8", "-B", "-m", PREFIX, "--help"],
                                    cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--demo", result.stdout)
        self.assertIn("--self-check", result.stdout)
