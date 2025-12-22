"""Static analysis for detecting dependencies between changes.

This module provides static analysis capabilities to detect dependencies
between changes based on code structure, imports, and references.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from git_bifurcate.models import FileChange, HunkChange


class DependencyAnalyzer:
    """Analyzes code changes to detect dependencies."""

    def __init__(self) -> None:
        """Initialize dependency analyzer."""
        self.symbol_definitions: dict[str, set[str]] = {}  # file_path -> {symbols}
        self.symbol_references: dict[str, set[str]] = {}  # file_path -> {symbols}

    def analyze_file_dependencies(self, changes: list[FileChange]) -> dict[str, list[str]]:
        """Analyze dependencies between file changes.

        Args:
            changes: List of FileChange objects to analyze.

        Returns:
            Dictionary mapping change IDs to lists of dependency IDs.
        """
        # Build symbol tables for each change
        for change in changes:
            self._extract_symbols(change)

        # Find dependencies
        dependencies: dict[str, list[str]] = {change.id: [] for change in changes}

        for change in changes:
            refs = self.symbol_references.get(change.file_path, set())

            # Check which other changes define symbols we reference
            for other_change in changes:
                if change.id == other_change.id:
                    continue

                defs = self.symbol_definitions.get(other_change.file_path, set())
                if refs & defs:  # If there's overlap
                    dependencies[change.id].append(other_change.id)

        return dependencies

    def analyze_hunk_dependencies(self, hunks: list[HunkChange]) -> dict[str, list[str]]:
        """Analyze dependencies between hunk changes.

        Args:
            hunks: List of HunkChange objects to analyze.

        Returns:
            Dictionary mapping hunk IDs to lists of dependency IDs.
        """
        # Extract symbols from each hunk
        hunk_symbols: dict[str, tuple[set[str], set[str]]] = {}

        for hunk in hunks:
            definitions, references = self._extract_hunk_symbols(hunk)
            hunk_symbols[hunk.id] = (definitions, references)

        # Find dependencies
        dependencies: dict[str, list[str]] = {hunk.id: [] for hunk in hunks}

        for hunk in hunks:
            _, refs = hunk_symbols[hunk.id]

            # Check which other hunks define symbols we reference
            for other_hunk in hunks:
                if hunk.id == other_hunk.id:
                    continue

                defs, _ = hunk_symbols[other_hunk.id]
                if refs & defs:
                    dependencies[hunk.id].append(other_hunk.id)

        return dependencies

    def _extract_symbols(self, change: FileChange) -> None:
        """Extract symbol definitions and references from a file change.

        Args:
            change: FileChange to analyze.
        """
        # Try language-specific analysis based on file extension
        if change.file_path.endswith(".py"):
            self._extract_python_symbols(change)
        elif change.file_path.endswith((".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx")):
            self._extract_cpp_symbols(change)
        elif change.file_path.endswith(".rs"):
            self._extract_rust_symbols(change)
        elif change.file_path.endswith(".go"):
            self._extract_go_symbols(change)
        elif change.file_path.endswith(".swift"):
            self._extract_swift_symbols(change)
        elif change.file_path.endswith(".zig"):
            self._extract_zig_symbols(change)
        elif change.file_path.endswith((".v", ".sv", ".vh", ".svh")):
            self._extract_verilog_symbols(change)
        else:
            # Fallback to generic analysis for other languages
            self._extract_generic_symbols(change)

    def _extract_python_symbols(self, change: FileChange) -> None:
        """Extract symbols using Python AST.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()

        # Parse diff to get added lines
        added_lines = self._extract_added_lines(change.diff_content)
        code = "\n".join(added_lines)

        try:
            tree = ast.parse(code)

            # Extract definitions (functions, classes, imports)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.ClassDef):
                    definitions.add(node.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        definitions.add(name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        definitions.add(node.module)
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        definitions.add(name)
                elif isinstance(node, ast.Name):
                    # References to names
                    if isinstance(node.ctx, ast.Load):
                        references.add(node.id)
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    # Handle attribute access (e.g., module.function)
                    references.add(node.value.id)

        except SyntaxError:
            # If parsing fails, fall back to regex
            self._extract_generic_symbols(change)
            return

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def _extract_generic_symbols(self, change: FileChange) -> None:
        """Extract symbols using regex patterns.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()

        added_lines = self._extract_added_lines(change.diff_content)

        for line in added_lines:
            # Look for function/class definitions (Python, JavaScript, etc.)
            if match := re.match(r"^\s*(?:def|class|function)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Look for imports (Python)
            if match := re.match(r"^\s*(?:import|from)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Look for identifiers (simple heuristic)
            identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
            references.update(identifiers)

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def _extract_hunk_symbols(self, hunk: HunkChange) -> tuple[set[str], set[str]]:
        """Extract symbols from a hunk.

        Args:
            hunk: HunkChange to analyze.

        Returns:
            Tuple of (definitions, references) sets.
        """
        definitions = set()
        references = set()

        added_lines = self._extract_added_lines(hunk.diff_content)

        if hunk.file_path.endswith(".py"):
            code = "\n".join(added_lines)
            try:
                tree = ast.parse(code)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef | ast.ClassDef):
                        definitions.add(node.name)
                    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                        references.add(node.id)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname if alias.asname else alias.name
                            definitions.add(name)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        references.add(node.module)

            except SyntaxError:
                # Fall back to regex
                for line in added_lines:
                    if match := re.match(r"^\s*(?:def|class)\s+(\w+)", line):
                        definitions.add(match.group(1))
                    identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
                    references.update(identifiers)
        else:
            # Generic analysis for non-Python files
            for line in added_lines:
                if match := re.match(r"^\s*(?:def|class|function)\s+(\w+)", line):
                    definitions.add(match.group(1))
                identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
                references.update(identifiers)

        return definitions, references

    def _extract_added_lines(self, diff_content: str) -> list[str]:
        """Extract lines that were added from diff content.

        Args:
            diff_content: Unified diff format content.

        Returns:
            List of added lines (without the '+' prefix).
        """
        added_lines = []
        for line in diff_content.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                # Remove the '+' prefix
                added_lines.append(line[1:])
        return added_lines

    def _extract_cpp_symbols(self, change: FileChange) -> None:
        """Extract symbols from C/C++ code.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()
        added_lines = self._extract_added_lines(change.diff_content)

        for line in added_lines:
            # Include directives
            if match := re.match(r'^\s*#include\s+[<"]([^>"]+)[>"]', line):
                header = match.group(1)
                # Extract base name without path and extension
                base = header.split("/")[-1].split(".")[0]
                references.add(base)

            # Function definitions/declarations
            if match := re.match(r"^\s*(?:static\s+)?(?:inline\s+)?(?:\w+\s+)+(\w+)\s*\(", line):
                definitions.add(match.group(1))

            # Class/struct definitions
            if match := re.match(r"^\s*(?:class|struct)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Namespace declarations
            if match := re.match(r"^\s*namespace\s+(\w+)", line):
                definitions.add(match.group(1))

            # Using declarations
            if match := re.match(r"^\s*using\s+(?:namespace\s+)?(\w+)", line):
                references.add(match.group(1))

            # Template definitions
            if match := re.match(r"^\s*template\s*<.*?>\s*(?:class|struct)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Extract identifiers (potential references)
            identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
            references.update(identifiers)

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def _extract_rust_symbols(self, change: FileChange) -> None:
        """Extract symbols from Rust code.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()
        added_lines = self._extract_added_lines(change.diff_content)

        for line in added_lines:
            # Use/extern statements
            if match := re.match(r"^\s*(?:use|extern\s+crate)\s+(\w+)", line):
                references.add(match.group(1))

            # Function definitions
            if match := re.match(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", line):
                definitions.add(match.group(1))

            # Struct/enum/trait definitions
            if match := re.match(r"^\s*(?:pub\s+)?(?:struct|enum|trait|type)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Impl blocks
            if match := re.match(r"^\s*impl(?:\s+<.*?>)?\s+(\w+)", line):
                references.add(match.group(1))

            # Mod declarations
            if match := re.match(r"^\s*(?:pub\s+)?mod\s+(\w+)", line):
                definitions.add(match.group(1))

            # Macro definitions
            if match := re.match(r"^\s*macro_rules!\s+(\w+)", line):
                definitions.add(match.group(1))

            # Extract identifiers
            identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
            references.update(identifiers)

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def _extract_go_symbols(self, change: FileChange) -> None:
        """Extract symbols from Go code.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()
        added_lines = self._extract_added_lines(change.diff_content)

        for line in added_lines:
            # Package declarations
            if match := re.match(r"^\s*package\s+(\w+)", line):
                definitions.add(match.group(1))

            # Import statements
            if match := re.match(r'^\s*(?:import\s+)?(?:"[^"]*?/)?(\w+)"', line):
                references.add(match.group(1))

            # Function definitions
            if match := re.match(r"^\s*func\s+(?:\([^)]*\)\s+)?(\w+)", line):
                definitions.add(match.group(1))

            # Type definitions
            if match := re.match(r"^\s*type\s+(\w+)", line):
                definitions.add(match.group(1))

            # Interface definitions
            if match := re.match(r"^\s*type\s+(\w+)\s+interface", line):
                definitions.add(match.group(1))

            # Struct definitions
            if match := re.match(r"^\s*type\s+(\w+)\s+struct", line):
                definitions.add(match.group(1))

            # Const/var declarations
            if match := re.match(r"^\s*(?:const|var)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Extract identifiers
            identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
            references.update(identifiers)

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def _extract_swift_symbols(self, change: FileChange) -> None:
        """Extract symbols from Swift code.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()
        added_lines = self._extract_added_lines(change.diff_content)

        for line in added_lines:
            # Import statements
            if match := re.match(r"^\s*import\s+(\w+)", line):
                references.add(match.group(1))

            # Class/struct/enum/protocol definitions
            if match := re.match(
                r"^\s*(?:public\s+|private\s+|internal\s+)?(?:class|struct|enum|protocol)\s+(\w+)",
                line,
            ):
                definitions.add(match.group(1))

            # Function definitions
            if match := re.match(r"^\s*(?:public\s+|private\s+)?func\s+(\w+)", line):
                definitions.add(match.group(1))

            # Property definitions
            if match := re.match(r"^\s*(?:let|var)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Extension declarations
            if match := re.match(r"^\s*extension\s+(\w+)", line):
                references.add(match.group(1))

            # Typealias
            if match := re.match(r"^\s*typealias\s+(\w+)", line):
                definitions.add(match.group(1))

            # Extract identifiers
            identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
            references.update(identifiers)

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def _extract_zig_symbols(self, change: FileChange) -> None:
        """Extract symbols from Zig code.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()
        added_lines = self._extract_added_lines(change.diff_content)

        for line in added_lines:
            # Import/use statements
            if match := re.match(r"^\s*const\s+(\w+)\s*=\s*@import", line):
                definitions.add(match.group(1))

            # Function definitions
            if match := re.match(r"^\s*(?:pub\s+)?fn\s+(\w+)", line):
                definitions.add(match.group(1))

            # Struct/enum/union definitions
            if match := re.match(r"^\s*(?:pub\s+)?const\s+(\w+)\s*=\s*(?:struct|enum|union)", line):
                definitions.add(match.group(1))

            # Type definitions
            if match := re.match(r"^\s*(?:pub\s+)?const\s+(\w+)\s*=\s*type", line):
                definitions.add(match.group(1))

            # Const/var declarations
            if match := re.match(r"^\s*(?:pub\s+)?(?:const|var)\s+(\w+)", line):
                definitions.add(match.group(1))

            # Extract identifiers
            identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
            references.update(identifiers)

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def _extract_verilog_symbols(self, change: FileChange) -> None:
        """Extract symbols from Verilog/SystemVerilog code.

        Args:
            change: FileChange to analyze.
        """
        definitions = set()
        references = set()
        added_lines = self._extract_added_lines(change.diff_content)

        for line in added_lines:
            # Include directives
            if match := re.match(r'^\s*`include\s+"([^"]+)"', line):
                header = match.group(1)
                base = header.split("/")[-1].split(".")[0]
                references.add(base)

            # Module definitions
            if match := re.match(r"^\s*module\s+(\w+)", line):
                definitions.add(match.group(1))

            # Package definitions
            if match := re.match(r"^\s*package\s+(\w+)", line):
                definitions.add(match.group(1))

            # Class definitions (SystemVerilog)
            if match := re.match(r"^\s*class\s+(\w+)", line):
                definitions.add(match.group(1))

            # Interface definitions
            if match := re.match(r"^\s*interface\s+(\w+)", line):
                definitions.add(match.group(1))

            # Function/task definitions
            if match := re.match(r"^\s*(?:function|task)\s+(?:\w+\s+)?(\w+)", line):
                definitions.add(match.group(1))

            # Import statements
            if match := re.match(r"^\s*import\s+(\w+)", line):
                references.add(match.group(1))

            # Parameter definitions
            if match := re.match(r"^\s*parameter\s+(?:\w+\s+)?(\w+)", line):
                definitions.add(match.group(1))

            # Extract identifiers
            identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", line)
            references.update(identifiers)

        self.symbol_definitions[change.file_path] = definitions
        self.symbol_references[change.file_path] = references

    def detect_import_dependencies(self, changes: list[FileChange]) -> dict[str, list[str]]:
        """Detect import-based dependencies between changes.

        Args:
            changes: List of FileChange objects.

        Returns:
            Dictionary mapping change IDs to dependency IDs.
        """
        dependencies: dict[str, list[str]] = {change.id: [] for change in changes}

        for change in changes:
            if not change.file_path.endswith(".py"):
                continue

            added_lines = self._extract_added_lines(change.diff_content)
            code = "\n".join(added_lines)

            try:
                tree = ast.parse(code)

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        # Convert module path to file path
                        module_parts = node.module.split(".")
                        # Try to find matching file in changes
                        for other_change in changes:
                            if other_change.id == change.id:
                                continue

                            other_path = Path(other_change.file_path)
                            # Simple heuristic: check if module name matches file
                            if any(part in other_path.stem for part in module_parts):
                                dependencies[change.id].append(other_change.id)

            except SyntaxError:
                pass

        return dependencies

    def detect_contextual_dependencies(self, hunks: list[HunkChange]) -> dict[str, list[str]]:
        """Detect dependencies based on line proximity and context.

        Hunks that modify nearby lines or the same logical block likely depend
        on each other.

        Args:
            hunks: List of HunkChange objects.

        Returns:
            Dictionary mapping hunk IDs to dependency IDs.
        """
        dependencies: dict[str, list[str]] = {hunk.id: [] for hunk in hunks}

        # Group hunks by file
        file_hunks: dict[str, list[HunkChange]] = {}
        for hunk in hunks:
            if hunk.file_path not in file_hunks:
                file_hunks[hunk.file_path] = []
            file_hunks[hunk.file_path].append(hunk)

        # Check proximity within each file
        for _file_path, file_hunk_list in file_hunks.items():
            for i, hunk1 in enumerate(file_hunk_list):
                for hunk2 in file_hunk_list[i + 1 :]:
                    # If hunks are within 5 lines, they may be dependent
                    if abs(hunk1.new_start - hunk2.new_start) <= 5:
                        # Earlier hunk is likely a dependency
                        if hunk1.new_start < hunk2.new_start:
                            dependencies[hunk2.id].append(hunk1.id)
                        else:
                            dependencies[hunk1.id].append(hunk2.id)

        return dependencies


def apply_dependency_analysis(changes: list[FileChange]) -> None:
    """Apply static dependency analysis to changes, updating their dependencies field.

    Args:
        changes: List of FileChange objects to analyze and update.
    """
    analyzer = DependencyAnalyzer()
    deps = analyzer.analyze_file_dependencies(changes)

    for change in changes:
        change.dependencies = deps.get(change.id, [])


def apply_hunk_dependency_analysis(hunks: list[HunkChange]) -> None:
    """Apply static dependency analysis to hunks, updating their dependencies field.

    Args:
        hunks: List of HunkChange objects to analyze and update.
    """
    analyzer = DependencyAnalyzer()
    deps = analyzer.analyze_hunk_dependencies(hunks)

    for hunk in hunks:
        hunk.dependencies = deps.get(hunk.id, [])
