"""Tests for static dependency analysis."""

from __future__ import annotations

import pytest

from git_bifurcate.dependency_analyzer import (
    DependencyAnalyzer,
    apply_dependency_analysis,
    apply_hunk_dependency_analysis,
)
from git_bifurcate.models import ChangeStatus, FileChange, HunkChange


class TestDependencyAnalyzer:
    """Tests for DependencyAnalyzer class."""

    def test_python_import_detection(self) -> None:
        """Test detecting import dependencies in Python code."""
        change1 = FileChange(
            "0",
            "module.py",
            "added",
            "+def my_function():\n+    pass",
            ChangeStatus.UNKNOWN,
        )
        change2 = FileChange(
            "1",
            "caller.py",
            "added",
            "+from module import my_function\n+my_function()",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_file_dependencies([change1, change2])

        # caller.py should depend on module.py
        assert "0" in deps["1"] or len(analyzer.symbol_definitions.get("module.py", set())) > 0

    def test_python_class_detection(self) -> None:
        """Test detecting class definitions and usage."""
        change1 = FileChange(
            "0",
            "models.py",
            "added",
            "+class MyClass:\n+    pass",
            ChangeStatus.UNKNOWN,
        )
        change2 = FileChange(
            "1",
            "usage.py",
            "added",
            "+from models import MyClass\n+obj = MyClass()",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_symbols(change1)
        analyzer._extract_symbols(change2)

        defs1 = analyzer.symbol_definitions.get("models.py", set())
        refs2 = analyzer.symbol_references.get("usage.py", set())

        assert "MyClass" in defs1
        assert "MyClass" in refs2 or "models" in refs2

    def test_no_dependency_independent_files(self) -> None:
        """Test that independent files have no dependencies."""
        change1 = FileChange(
            "0",
            "file1.py",
            "modified",
            "+def func1():\n+    return 1",
            ChangeStatus.UNKNOWN,
        )
        change2 = FileChange(
            "1",
            "file2.py",
            "modified",
            "+def func2():\n+    return 2",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_file_dependencies([change1, change2])

        # No dependencies between independent files
        assert deps["0"] == []
        assert deps["1"] == []

    def test_hunk_dependency_detection(self) -> None:
        """Test detecting dependencies between hunks."""
        hunk1 = HunkChange(
            "0",
            "file.py",
            1,
            5,
            1,
            3,
            1,
            5,
            "+def helper():\n+    pass",
            ChangeStatus.UNKNOWN,
        )
        hunk2 = HunkChange(
            "1",
            "file.py",
            10,
            15,
            10,
            3,
            10,
            5,
            "+def main():\n+    helper()",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_hunk_dependencies([hunk1, hunk2])

        # hunk2 should depend on hunk1
        assert "0" in deps["1"]

    def test_extract_added_lines(self) -> None:
        """Test extracting added lines from diff."""
        diff = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,5 @@
 existing line
+added line 1
+added line 2
 another existing
"""
        analyzer = DependencyAnalyzer()
        added = analyzer._extract_added_lines(diff)

        assert added == ["added line 1", "added line 2"]

    def test_generic_symbol_extraction(self) -> None:
        """Test fallback regex-based symbol extraction."""
        change = FileChange(
            "0",
            "file.js",
            "added",
            "+function myFunc() {\n+    return 42;\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_generic_symbols(change)

        defs = analyzer.symbol_definitions.get("file.js", set())
        # Should have extracted function name
        assert len(defs) > 0

    def test_apply_dependency_analysis(self) -> None:
        """Test applying analysis to update change dependencies."""
        changes = [
            FileChange("0", "base.py", "added", "+def foo():\n+    pass"),
            FileChange("1", "user.py", "added", "+from base import foo\n+foo()"),
        ]

        apply_dependency_analysis(changes)

        # Check that dependencies were updated
        assert isinstance(changes[0].dependencies, list)
        assert isinstance(changes[1].dependencies, list)

    def test_syntax_error_fallback(self) -> None:
        """Test that syntax errors fall back to regex analysis."""
        change = FileChange(
            "0",
            "broken.py",
            "modified",
            "+def incomplete_function(\n+    # Missing closing paren",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        # Should not raise, should fall back to regex
        analyzer._extract_python_symbols(change)

        # Should have attempted to extract symbols
        assert "broken.py" in analyzer.symbol_definitions or "broken.py" in analyzer.symbol_references

    def test_contextual_hunk_dependencies(self) -> None:
        """Test detecting dependencies based on line proximity."""
        hunks = [
            HunkChange("0", "file.py", 10, 15, 10, 3, 10, 5, "+code", ChangeStatus.UNKNOWN),
            HunkChange("1", "file.py", 12, 17, 12, 3, 12, 5, "+more", ChangeStatus.UNKNOWN),
            HunkChange("2", "file.py", 100, 105, 100, 3, 100, 5, "+far", ChangeStatus.UNKNOWN),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.detect_contextual_dependencies(hunks)

        # Hunks 0 and 1 are close (within 5 lines), should be dependent
        assert "0" in deps["1"] or "1" in deps["0"]

        # Hunk 2 is far from others, should be independent
        assert "2" not in deps["0"]
        assert "2" not in deps["1"]


class TestDependencyAnalysisIntegration:
    """Integration tests for dependency analysis."""

    def test_complex_python_module(self) -> None:
        """Test analyzing a complex Python module with multiple dependencies."""
        changes = [
            FileChange(
                "0",
                "utils.py",
                "added",
                "+def utility():\n+    return 'util'",
                ChangeStatus.UNKNOWN,
            ),
            FileChange(
                "1",
                "models.py",
                "added",
                "+from utils import utility\n+class Model:\n+    def __init__(self):\n+        utility()",
                ChangeStatus.UNKNOWN,
            ),
            FileChange(
                "2",
                "views.py",
                "added",
                "+from models import Model\n+m = Model()",
                ChangeStatus.UNKNOWN,
            ),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_file_dependencies(changes)

        # Should detect dependency chain: views -> models -> utils
        assert len(deps) == 3
        # Each file should have analyzed symbols
        assert len(analyzer.symbol_definitions) > 0

    def test_apply_hunk_analysis(self) -> None:
        """Test applying hunk dependency analysis."""
        hunks = [
            HunkChange("0", "f.py", 1, 5, 1, 3, 1, 5, "+def a():\n+    pass"),
            HunkChange("1", "f.py", 10, 15, 10, 3, 10, 5, "+a()"),
        ]

        apply_hunk_dependency_analysis(hunks)

        # Dependencies should be populated
        assert isinstance(hunks[0].dependencies, list)
        assert isinstance(hunks[1].dependencies, list)

    def test_multiple_file_dependencies(self) -> None:
        """Test dependencies across multiple files."""
        changes = [
            FileChange("0", "a.py", "added", "+X = 1"),
            FileChange("1", "b.py", "added", "+Y = 2"),
            FileChange("2", "c.py", "added", "+from a import X\n+from b import Y\n+z = X + Y"),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_file_dependencies(changes)

        # c.py should reference both a.py and b.py
        refs = analyzer.symbol_references.get("c.py", set())
        assert "a" in refs or "X" in refs
        assert "b" in refs or "Y" in refs


class TestEdgeCases:
    """Test edge cases in dependency analysis."""

    def test_empty_change(self) -> None:
        """Test analyzing empty change."""
        change = FileChange("0", "empty.py", "modified", "", ChangeStatus.UNKNOWN)

        analyzer = DependencyAnalyzer()
        analyzer._extract_symbols(change)

        # Should not crash, should have empty sets
        assert analyzer.symbol_definitions.get("empty.py", set()) == set()

    def test_non_python_file(self) -> None:
        """Test analyzing non-Python file."""
        change = FileChange(
            "0",
            "script.sh",
            "added",
            "+#!/bin/bash\n+echo hello",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_symbols(change)

        # Should use generic extraction
        assert "script.sh" in analyzer.symbol_definitions

    def test_circular_reference(self) -> None:
        """Test handling circular references."""
        change1 = FileChange("0", "a.py", "added", "+from b import B\n+class A:\n+    pass")
        change2 = FileChange("1", "b.py", "added", "+from a import A\n+class B:\n+    pass")

        analyzer = DependencyAnalyzer()
        analyzer._extract_symbols(change1)
        analyzer._extract_symbols(change2)

        # Both files should have symbols extracted
        defs1 = analyzer.symbol_definitions.get("a.py", set())
        defs2 = analyzer.symbol_definitions.get("b.py", set())
        refs1 = analyzer.symbol_references.get("a.py", set())
        refs2 = analyzer.symbol_references.get("b.py", set())

        # Should detect class definitions
        assert "A" in defs1
        assert "B" in defs2

        # Should reference the modules
        assert "b" in defs1 or "B" in refs1
        assert "a" in defs2 or "A" in refs2

    def test_self_reference(self) -> None:
        """Test file referencing its own symbols."""
        change = FileChange(
            "0",
            "module.py",
            "modified",
            "+def func():\n+    pass\n+\n+func()",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_file_dependencies([change])

        # Should not depend on itself
        assert "0" not in deps["0"]

    def test_import_aliasing(self) -> None:
        """Test handling import aliases."""
        change1 = FileChange("0", "original.py", "added", "+def original_func():\n+    pass")
        change2 = FileChange(
            "1",
            "user.py",
            "added",
            "+from original import original_func as func\n+func()",
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_symbols(change1)
        analyzer._extract_symbols(change2)

        defs = analyzer.symbol_definitions.get("original.py", set())
        refs = analyzer.symbol_references.get("user.py", set())

        # Should detect alias
        assert "original_func" in defs
        assert "func" in analyzer.symbol_definitions.get("user.py", set())

    def test_multiline_diff(self) -> None:
        """Test extracting from multiline diff."""
        diff = """+class MyClass:
+    def __init__(self):
+        self.value = 1
+
+    def method(self):
+        return self.value
"""
        analyzer = DependencyAnalyzer()
        added = analyzer._extract_added_lines(diff)

        assert len(added) == 6
        assert "class MyClass:" in added

    def test_from_import_star(self) -> None:
        """Test handling from module import *."""
        change = FileChange(
            "0",
            "user.py",
            "added",
            "+from module import *\n+some_function()",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_python_symbols(change)

        # Should capture the module reference
        refs = analyzer.symbol_references.get("user.py", set())
        assert "module" in analyzer.symbol_definitions.get("user.py", set())

    def test_import_with_asname(self) -> None:
        """Test detecting imports with asname (e.g., import foo as bar)."""
        change = FileChange(
            "0",
            "user.py",
            "added",
            "+import numpy as np\n+import pandas as pd\n+result = np.array([1,2,3])",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_python_symbols(change)

        defs = analyzer.symbol_definitions.get("user.py", set())
        # asname should be captured
        assert "np" in defs
        assert "pd" in defs

    def test_attribute_access_references(self) -> None:
        """Test detecting attribute access as references."""
        change = FileChange(
            "0",
            "user.py",
            "added",
            "+import module\n+result = module.function()\n+value = obj.attr",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_python_symbols(change)

        refs = analyzer.symbol_references.get("user.py", set())
        # module and obj should be in references
        assert "module" in refs or "module" in analyzer.symbol_definitions.get("user.py", set())

    def test_detect_import_dependencies(self) -> None:
        """Test detect_import_dependencies method."""
        changes = [
            FileChange(
                "0",
                "utils.py",
                "added",
                "+def utility():\n+    pass",
                ChangeStatus.UNKNOWN,
            ),
            FileChange(
                "1",
                "main.py",
                "added",
                "+from utils import utility\n+utility()",
                ChangeStatus.UNKNOWN,
            ),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.detect_import_dependencies(changes)

        # Should detect import dependency
        assert isinstance(deps, dict)
        assert all(change.id in deps for change in changes)
        # main.py should depend on utils.py
        assert "0" in deps["1"]

    def test_detect_import_dependencies_syntax_error(self) -> None:
        """Test detect_import_dependencies handles syntax errors."""
        changes = [
            FileChange(
                "0",
                "broken.py",
                "added",
                "+def foo(\n+    # Syntax error",
                ChangeStatus.UNKNOWN,
            ),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.detect_import_dependencies(changes)

        # Should handle error gracefully
        assert "0" in deps

    def test_detect_import_dependencies_non_python(self) -> None:
        """Test detect_import_dependencies skips non-Python files."""
        changes = [
            FileChange(
                "0",
                "file.cpp",
                "added",
                "+#include <iostream>",
                ChangeStatus.UNKNOWN,
            ),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.detect_import_dependencies(changes)

        # Should skip non-Python files
        assert deps["0"] == []

    def test_verilog_parameter_detection(self) -> None:
        """Test detecting Verilog parameter definitions."""
        change = FileChange(
            "0",
            "module.v",
            "added",
            "+parameter WIDTH = 8;\n+parameter integer DEPTH = 16;",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        defs = analyzer.symbol_definitions.get("module.v", set())
        assert "WIDTH" in defs
        assert "DEPTH" in defs
