"""Tests for multi-language dependency detection.

Covers C/C++, Rust, Go, Swift, Zig, and Verilog/SystemVerilog.
"""

from __future__ import annotations

from git_bifurcate.dependency_analyzer import DependencyAnalyzer
from git_bifurcate.models import ChangeStatus, FileChange, HunkChange


class TestCppDependencies:
    """Tests for C/C++ dependency detection."""

    def test_include_detection(self) -> None:
        """Test detecting #include directives."""
        change = FileChange(
            "0",
            "main.cpp",
            "added",
            '+#include "utils.h"\n+#include <vector>',
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        refs = analyzer.symbol_references.get("main.cpp", set())
        assert "utils" in refs
        assert "vector" in refs

    def test_function_definition(self) -> None:
        """Test detecting function definitions."""
        change = FileChange(
            "0",
            "utils.cpp",
            "added",
            "+void processData() {\n+    // impl\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        defs = analyzer.symbol_definitions.get("utils.cpp", set())
        assert "processData" in defs

    def test_class_definition(self) -> None:
        """Test detecting class definitions."""
        change = FileChange(
            "0",
            "MyClass.h",
            "added",
            "+class MyClass {\n+public:\n+    void method();\n+};",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        defs = analyzer.symbol_definitions.get("MyClass.h", set())
        assert "MyClass" in defs
        assert "method" in defs

    def test_namespace_detection(self) -> None:
        """Test detecting namespace declarations."""
        change = FileChange(
            "0",
            "utils.h",
            "added",
            "+namespace utils {\n+    void helper();\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        defs = analyzer.symbol_definitions.get("utils.h", set())
        assert "utils" in defs
        assert "helper" in defs

    def test_using_declaration(self) -> None:
        """Test detecting using declarations."""
        change = FileChange(
            "0",
            "main.cpp",
            "added",
            "+using namespace std;\n+using MyType = int;",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        refs = analyzer.symbol_references.get("main.cpp", set())
        assert "std" in refs

    def test_template_class(self) -> None:
        """Test detecting template class definitions."""
        change = FileChange(
            "0",
            "container.h",
            "added",
            "+template <typename T>\n+class Container {\n+};",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        defs = analyzer.symbol_definitions.get("container.h", set())
        assert "Container" in defs


class TestRustDependencies:
    """Tests for Rust dependency detection."""

    def test_use_statement(self) -> None:
        """Test detecting use statements."""
        change = FileChange(
            "0",
            "main.rs",
            "added",
            "+use std::collections::HashMap;\n+use crate::utils;",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        refs = analyzer.symbol_references.get("main.rs", set())
        assert "std" in refs
        assert "crate" in refs

    def test_function_definition(self) -> None:
        """Test detecting function definitions."""
        change = FileChange(
            "0",
            "lib.rs",
            "added",
            "+pub fn process_data() -> Result<()> {\n+    Ok(())\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        defs = analyzer.symbol_definitions.get("lib.rs", set())
        assert "process_data" in defs

    def test_struct_definition(self) -> None:
        """Test detecting struct definitions."""
        change = FileChange(
            "0",
            "models.rs",
            "added",
            "+pub struct User {\n+    name: String,\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        defs = analyzer.symbol_definitions.get("models.rs", set())
        assert "User" in defs

    def test_enum_definition(self) -> None:
        """Test detecting enum definitions."""
        change = FileChange(
            "0",
            "types.rs",
            "added",
            "+pub enum Status {\n+    Active,\n+    Inactive,\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        defs = analyzer.symbol_definitions.get("types.rs", set())
        assert "Status" in defs

    def test_trait_definition(self) -> None:
        """Test detecting trait definitions."""
        change = FileChange(
            "0",
            "traits.rs",
            "added",
            "+pub trait Processor {\n+    fn process(&self);\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        defs = analyzer.symbol_definitions.get("traits.rs", set())
        assert "Processor" in defs
        assert "process" in defs

    def test_impl_block(self) -> None:
        """Test detecting impl blocks."""
        change = FileChange(
            "0",
            "impl.rs",
            "added",
            "+impl MyStruct {\n+    fn new() -> Self {\n+    }\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        refs = analyzer.symbol_references.get("impl.rs", set())
        assert "MyStruct" in refs

    def test_mod_declaration(self) -> None:
        """Test detecting mod declarations."""
        change = FileChange(
            "0",
            "lib.rs",
            "added",
            "+pub mod utils;\n+mod private;",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        defs = analyzer.symbol_definitions.get("lib.rs", set())
        assert "utils" in defs
        assert "private" in defs

    def test_macro_definition(self) -> None:
        """Test detecting macro definitions."""
        change = FileChange(
            "0",
            "macros.rs",
            "added",
            "+macro_rules! my_macro {\n+    () => {};\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_rust_symbols(change)

        defs = analyzer.symbol_definitions.get("macros.rs", set())
        assert "my_macro" in defs


class TestGoDependencies:
    """Tests for Go dependency detection."""

    def test_package_declaration(self) -> None:
        """Test detecting package declarations."""
        change = FileChange(
            "0",
            "main.go",
            "added",
            "+package main",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        defs = analyzer.symbol_definitions.get("main.go", set())
        assert "main" in defs

    def test_import_statement(self) -> None:
        """Test detecting import statements."""
        change = FileChange(
            "0",
            "main.go",
            "added",
            '+import "fmt"\n+import "github.com/user/repo/utils"',
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        refs = analyzer.symbol_references.get("main.go", set())
        assert "fmt" in refs
        assert "utils" in refs

    def test_function_definition(self) -> None:
        """Test detecting function definitions."""
        change = FileChange(
            "0",
            "utils.go",
            "added",
            "+func ProcessData(data string) error {\n+    return nil\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        defs = analyzer.symbol_definitions.get("utils.go", set())
        assert "ProcessData" in defs

    def test_method_definition(self) -> None:
        """Test detecting method definitions."""
        change = FileChange(
            "0",
            "types.go",
            "added",
            "+func (s *MyStruct) Method() {\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        defs = analyzer.symbol_definitions.get("types.go", set())
        assert "Method" in defs

    def test_type_definition(self) -> None:
        """Test detecting type definitions."""
        change = FileChange(
            "0",
            "types.go",
            "added",
            "+type UserID int64",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        defs = analyzer.symbol_definitions.get("types.go", set())
        assert "UserID" in defs

    def test_struct_definition(self) -> None:
        """Test detecting struct definitions."""
        change = FileChange(
            "0",
            "models.go",
            "added",
            "+type User struct {\n+    Name string\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        defs = analyzer.symbol_definitions.get("models.go", set())
        assert "User" in defs

    def test_interface_definition(self) -> None:
        """Test detecting interface definitions."""
        change = FileChange(
            "0",
            "interfaces.go",
            "added",
            "+type Processor interface {\n+    Process() error\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        defs = analyzer.symbol_definitions.get("interfaces.go", set())
        assert "Processor" in defs


class TestSwiftDependencies:
    """Tests for Swift dependency detection."""

    def test_import_statement(self) -> None:
        """Test detecting import statements."""
        change = FileChange(
            "0",
            "main.swift",
            "added",
            "+import Foundation\n+import UIKit",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        refs = analyzer.symbol_references.get("main.swift", set())
        assert "Foundation" in refs
        assert "UIKit" in refs

    def test_class_definition(self) -> None:
        """Test detecting class definitions."""
        change = FileChange(
            "0",
            "MyClass.swift",
            "added",
            "+public class MyClass {\n+    init() {}\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        defs = analyzer.symbol_definitions.get("MyClass.swift", set())
        assert "MyClass" in defs

    def test_struct_definition(self) -> None:
        """Test detecting struct definitions."""
        change = FileChange(
            "0",
            "Models.swift",
            "added",
            "+struct User {\n+    var name: String\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        defs = analyzer.symbol_definitions.get("Models.swift", set())
        assert "User" in defs

    def test_enum_definition(self) -> None:
        """Test detecting enum definitions."""
        change = FileChange(
            "0",
            "Types.swift",
            "added",
            "+enum Status {\n+    case active, inactive\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        defs = analyzer.symbol_definitions.get("Types.swift", set())
        assert "Status" in defs

    def test_protocol_definition(self) -> None:
        """Test detecting protocol definitions."""
        change = FileChange(
            "0",
            "Protocols.swift",
            "added",
            "+protocol Processor {\n+    func process()\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        defs = analyzer.symbol_definitions.get("Protocols.swift", set())
        assert "Processor" in defs

    def test_function_definition(self) -> None:
        """Test detecting function definitions."""
        change = FileChange(
            "0",
            "Utils.swift",
            "added",
            "+public func processData() -> Bool {\n+    return true\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        defs = analyzer.symbol_definitions.get("Utils.swift", set())
        assert "processData" in defs

    def test_extension_declaration(self) -> None:
        """Test detecting extension declarations."""
        change = FileChange(
            "0",
            "Extensions.swift",
            "added",
            "+extension String {\n+    func trimmed() -> String {}\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        refs = analyzer.symbol_references.get("Extensions.swift", set())
        assert "String" in refs


class TestZigDependencies:
    """Tests for Zig dependency detection."""

    def test_import_statement(self) -> None:
        """Test detecting import statements."""
        change = FileChange(
            "0",
            "main.zig",
            "added",
            '+const std = @import("std");',
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_zig_symbols(change)

        defs = analyzer.symbol_definitions.get("main.zig", set())
        assert "std" in defs

    def test_function_definition(self) -> None:
        """Test detecting function definitions."""
        change = FileChange(
            "0",
            "utils.zig",
            "added",
            "+pub fn processData() void {\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_zig_symbols(change)

        defs = analyzer.symbol_definitions.get("utils.zig", set())
        assert "processData" in defs

    def test_struct_definition(self) -> None:
        """Test detecting struct definitions."""
        change = FileChange(
            "0",
            "types.zig",
            "added",
            "+pub const User = struct {\n+    name: []const u8,\n+};",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_zig_symbols(change)

        defs = analyzer.symbol_definitions.get("types.zig", set())
        assert "User" in defs

    def test_enum_definition(self) -> None:
        """Test detecting enum definitions."""
        change = FileChange(
            "0",
            "types.zig",
            "added",
            "+const Status = enum {\n+    active,\n+    inactive,\n+};",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_zig_symbols(change)

        defs = analyzer.symbol_definitions.get("types.zig", set())
        assert "Status" in defs

    def test_const_declaration(self) -> None:
        """Test detecting const declarations."""
        change = FileChange(
            "0",
            "config.zig",
            "added",
            '+pub const VERSION = "1.0.0";',
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_zig_symbols(change)

        defs = analyzer.symbol_definitions.get("config.zig", set())
        assert "VERSION" in defs


class TestVerilogDependencies:
    """Tests for Verilog/SystemVerilog dependency detection."""

    def test_include_directive(self) -> None:
        """Test detecting include directives."""
        change = FileChange(
            "0",
            "top.v",
            "added",
            '+`include "defs.vh"\n+`include "pkg/utils.svh"',
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        refs = analyzer.symbol_references.get("top.v", set())
        assert "defs" in refs
        assert "utils" in refs

    def test_module_definition(self) -> None:
        """Test detecting module definitions."""
        change = FileChange(
            "0",
            "counter.v",
            "added",
            "+module counter(\n+    input clk,\n+    output reg [7:0] count\n+);",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        defs = analyzer.symbol_definitions.get("counter.v", set())
        assert "counter" in defs

    def test_package_definition(self) -> None:
        """Test detecting package definitions."""
        change = FileChange(
            "0",
            "pkg.sv",
            "added",
            "+package my_pkg;\n+    typedef logic [7:0] byte_t;\n+endpackage",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        defs = analyzer.symbol_definitions.get("pkg.sv", set())
        assert "my_pkg" in defs

    def test_class_definition(self) -> None:
        """Test detecting class definitions (SystemVerilog)."""
        change = FileChange(
            "0",
            "transaction.sv",
            "added",
            "+class transaction;\n+    rand bit [7:0] data;\n+endclass",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        defs = analyzer.symbol_definitions.get("transaction.sv", set())
        assert "transaction" in defs

    def test_interface_definition(self) -> None:
        """Test detecting interface definitions."""
        change = FileChange(
            "0",
            "bus_if.sv",
            "added",
            "+interface bus_if;\n+    logic clk;\n+    logic [7:0] data;\n+endinterface",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        defs = analyzer.symbol_definitions.get("bus_if.sv", set())
        assert "bus_if" in defs

    def test_function_definition(self) -> None:
        """Test detecting function definitions."""
        change = FileChange(
            "0",
            "utils.sv",
            "added",
            "+function int calculate(int a, int b);\n+    return a + b;\n+endfunction",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        defs = analyzer.symbol_definitions.get("utils.sv", set())
        assert "calculate" in defs

    def test_import_statement(self) -> None:
        """Test detecting import statements."""
        change = FileChange(
            "0",
            "top.sv",
            "added",
            "+import my_pkg::*;\n+import uvm_pkg::uvm_component;",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        refs = analyzer.symbol_references.get("top.sv", set())
        assert "my_pkg" in refs
        assert "uvm_pkg" in refs


class TestCrosslanguageDependencies:
    """Test dependency detection across multiple languages."""

    def test_mixed_language_project(self) -> None:
        """Test analyzing dependencies in a mixed-language project."""
        changes = [
            FileChange("0", "utils.cpp", "added", "+void processData() {}", ChangeStatus.UNKNOWN),
            FileChange("1", "main.rs", "added", "+pub fn main() {}", ChangeStatus.UNKNOWN),
            FileChange("2", "app.swift", "added", "+func run() {}", ChangeStatus.UNKNOWN),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_file_dependencies(changes)

        # Should handle all languages without errors
        assert len(deps) == 3
        assert all(isinstance(deps[cid], list) for cid in ["0", "1", "2"])

    def test_language_specific_patterns(self) -> None:
        """Test that each language extracts its specific patterns correctly."""
        test_cases = [
            ("file.cpp", '+#include "header.h"', "header"),
            ("file.rs", "+use std::io;", "std"),
            ("file.go", '+import "fmt"', "fmt"),
            ("file.swift", "+import Foundation", "Foundation"),
            ("file.zig", '+const std = @import("std");', "std"),
            ("file.sv", '+`include "defs.vh"', "defs"),
        ]

        analyzer = DependencyAnalyzer()

        for file_path, diff, expected_symbol in test_cases:
            change = FileChange("0", file_path, "added", diff, ChangeStatus.UNKNOWN)
            analyzer._extract_symbols(change)

            symbols = analyzer.symbol_definitions.get(
                file_path, set()
            ) | analyzer.symbol_references.get(file_path, set())
            assert expected_symbol in symbols, f"Failed for {file_path}: expected {expected_symbol}"

    def test_cpp_template_definition(self) -> None:
        """Test C++ template class/struct definitions."""
        change = FileChange(
            "0",
            "template.h",
            "added",
            "+template <typename T>\n+class Container {\n+    T value;\n+};",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        defs = analyzer.symbol_definitions.get("template.h", set())
        assert "Container" in defs

    def test_go_var_definition(self) -> None:
        """Test Go variable definitions."""
        change = FileChange(
            "0",
            "vars.go",
            "added",
            "+var GlobalVar = 42\n+var AnotherVar string",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_go_symbols(change)

        defs = analyzer.symbol_definitions.get("vars.go", set())
        assert "GlobalVar" in defs or "AnotherVar" in defs

    def test_swift_protocol_definition(self) -> None:
        """Test Swift protocol definitions."""
        change = FileChange(
            "0",
            "protocol.swift",
            "added",
            "+protocol MyProtocol {\n+    func doSomething()\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        defs = analyzer.symbol_definitions.get("protocol.swift", set())
        assert "MyProtocol" in defs

    def test_zig_pub_fn_definition(self) -> None:
        """Test Zig public function definitions."""
        change = FileChange(
            "0",
            "module.zig",
            "added",
            "+pub fn publicFunction() void {\n+    return;\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_zig_symbols(change)

        defs = analyzer.symbol_definitions.get("module.zig", set())
        assert "publicFunction" in defs

    def test_verilog_module_definition(self) -> None:
        """Test Verilog module definitions."""
        change = FileChange(
            "0",
            "design.v",
            "added",
            "+module counter(\n+    input clk,\n+    output [7:0] count\n+);",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_verilog_symbols(change)

        defs = analyzer.symbol_definitions.get("design.v", set())
        assert "counter" in defs

    def test_hunk_import_analysis(self) -> None:
        """Test hunk-level Python import analysis."""
        hunk = HunkChange(
            "0",
            "module.py",
            1,
            10,
            1,
            3,
            1,
            10,
            "+import numpy as np\n+from typing import List\n+x = np.array([1,2,3])",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        defs, refs = analyzer._extract_hunk_symbols(hunk)

        # Should capture import with asname
        assert "np" in defs or "List" in refs

    def test_hunk_syntax_error_fallback(self) -> None:
        """Test hunk analysis falls back to regex on syntax error."""
        hunk = HunkChange(
            "0",
            "broken.py",
            1,
            5,
            1,
            2,
            1,
            5,
            "+def incomplete(\n+    # syntax error",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        defs, _refs = analyzer._extract_hunk_symbols(hunk)

        # Should use fallback regex
        assert "incomplete" in defs

    def test_hunk_non_python_generic(self) -> None:
        """Test hunk analysis for non-Python files."""
        hunk = HunkChange(
            "0",
            "module.js",
            1,
            5,
            1,
            2,
            1,
            5,
            "+function myFunc() {\n+    return 42;\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        defs, _refs = analyzer._extract_hunk_symbols(hunk)

        # Should use generic extraction
        assert "myFunc" in defs

    def test_generic_extraction_import_pattern(self) -> None:
        """Test generic import pattern extraction."""
        change = FileChange(
            "0",
            "module.unknown",
            "added",
            "+import somemodule\n+from another import thing",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_generic_symbols(change)

        defs = analyzer.symbol_definitions.get("module.unknown", set())
        # Should capture import modules
        assert "somemodule" in defs or "another" in defs

    def test_contextual_hunk_dependencies(self) -> None:
        """Test detecting contextual dependencies between hunks."""
        hunks = [
            HunkChange("0", "f.py", 1, 5, 1, 3, 1, 5, "+def helper():\n+    pass"),
            HunkChange("1", "f.py", 10, 15, 10, 2, 10, 5, "+result = helper()"),
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.detect_contextual_dependencies(hunks)

        # Should return a dict with all hunk ids
        assert "0" in deps
        assert "1" in deps
        assert isinstance(deps, dict)

    def test_cpp_template_class(self) -> None:
        """Test C++ template class definitions."""
        change = FileChange(
            "0",
            "template.h",
            "added",
            "+template <typename T> class MyTemplate { T value; };",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_cpp_symbols(change)

        defs = analyzer.symbol_definitions.get("template.h", set())
        assert "MyTemplate" in defs

    def test_swift_typealias(self) -> None:
        """Test Swift typealias definitions."""
        change = FileChange(
            "0",
            "types.swift",
            "added",
            "+typealias StringDictionary = [String: String]\n+typealias Callback = () -> Void",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_swift_symbols(change)

        defs = analyzer.symbol_definitions.get("types.swift", set())
        assert "StringDictionary" in defs or "Callback" in defs

    def test_zig_type_definition(self) -> None:
        """Test Zig type definitions."""
        change = FileChange(
            "0",
            "types.zig",
            "added",
            "+const MyType = type;\n+pub const PublicType = type;",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()
        analyzer._extract_zig_symbols(change)

        defs = analyzer.symbol_definitions.get("types.zig", set())
        assert "MyType" in defs or "PublicType" in defs

    def test_contextual_dependencies_reverse_order(self) -> None:
        """Test contextual dependencies when later hunk starts earlier in file."""
        hunks = [
            HunkChange(
                "0", "f.py", 1, 5, 5, 2, 5, 5, "+result = helper()"
            ),  # Starts at line 5 in new file
            HunkChange(
                "1", "f.py", 10, 15, 1, 3, 1, 5, "+def helper():\n+    pass"
            ),  # Starts at line 1 in new file
        ]

        analyzer = DependencyAnalyzer()
        deps = analyzer.detect_contextual_dependencies(hunks)

        # Should detect dependency - hunks are within 5 lines and hunk 1 starts earlier
        assert "0" in deps
        assert "1" in deps
        # Hunk 0 should depend on hunk 1 since hunk 1 starts earlier (line 1 vs line 5)
        assert "1" in deps["0"]
