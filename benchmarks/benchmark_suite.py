"""Comprehensive benchmark suite for git-bifurcate.

Benchmarks for performance regression testing across:
- Dependency detection (static analysis)
- Binary search algorithms
- Dependency graph operations
- Cache effectiveness
- Multi-language parsing
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from git_bifurcate.core import BifurcationEngine
from git_bifurcate.dependency_analyzer import DependencyAnalyzer
from git_bifurcate.dependency_graph import DependencyGraph
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import ChangeStatus, CommandResult, FileChange, HunkChange
from git_bifurcate.test_runner import CommandRunner


@dataclass
class BenchmarkResult:
    """Result from a benchmark run."""

    name: str
    duration_ms: float
    iterations: int
    ops_per_sec: float
    metadata: dict[str, Any]


class BenchmarkRunner:
    """Runs and records benchmarks."""

    def __init__(self) -> None:
        """Initialize benchmark runner."""
        self.results: list[BenchmarkResult] = []

    def run_benchmark(
        self,
        name: str,
        func: Callable[[], None],
        iterations: int = 100,
        warmup: int = 10,
        **metadata: Any,
    ) -> BenchmarkResult:
        """Run a benchmark function.

        Args:
            name: Name of the benchmark.
            func: Function to benchmark.
            iterations: Number of iterations to run.
            warmup: Number of warmup iterations.
            metadata: Additional metadata to record.

        Returns:
            BenchmarkResult with timing information.
        """
        # Warmup
        for _ in range(warmup):
            func()

        # Actual benchmark
        start = time.perf_counter()
        for _ in range(iterations):
            func()
        end = time.perf_counter()

        duration_ms = (end - start) * 1000
        ops_per_sec = iterations / (end - start) if end > start else 0

        result = BenchmarkResult(
            name=name,
            duration_ms=duration_ms,
            iterations=iterations,
            ops_per_sec=ops_per_sec,
            metadata=metadata,
        )

        self.results.append(result)
        return result

    def print_results(self) -> None:
        """Print all benchmark results in a formatted table."""
        print("\n" + "=" * 80)
        print("BENCHMARK RESULTS")
        print("=" * 80)
        print(f"{'Benchmark':<50} {'Time (ms)':<12} {'Ops/sec':<12}")
        print("-" * 80)

        for result in self.results:
            print(
                f"{result.name:<50} {result.duration_ms:>11.2f} {result.ops_per_sec:>11.0f}"
            )

        print("=" * 80 + "\n")

    def save_results(self, filepath: str) -> None:
        """Save results to a JSON file for tracking over time.

        Args:
            filepath: Path to save results to.
        """
        import json

        data = [
            {
                "name": r.name,
                "duration_ms": r.duration_ms,
                "iterations": r.iterations,
                "ops_per_sec": r.ops_per_sec,
                "metadata": r.metadata,
                "timestamp": time.time(),
            }
            for r in self.results
        ]

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)


class DependencyAnalysisBenchmarks:
    """Benchmarks for dependency analysis."""

    def __init__(self, runner: BenchmarkRunner) -> None:
        """Initialize dependency analysis benchmarks.

        Args:
            runner: Benchmark runner to use.
        """
        self.runner = runner

    def run_all(self) -> None:
        """Run all dependency analysis benchmarks."""
        self.bench_python_analysis()
        self.bench_cpp_analysis()
        self.bench_rust_analysis()
        self.bench_go_analysis()
        self.bench_mixed_language()
        self.bench_large_file_set()

    def bench_python_analysis(self) -> None:
        """Benchmark Python code analysis."""
        change = FileChange(
            "0",
            "module.py",
            "added",
            "+def function1():\n+    pass\n+\n+class MyClass:\n+    def method(self):\n+        function1()",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()

        self.runner.run_benchmark(
            "Python AST Analysis",
            lambda: analyzer._extract_python_symbols(change),
            iterations=1000,
            language="python",
        )

    def bench_cpp_analysis(self) -> None:
        """Benchmark C++ code analysis."""
        change = FileChange(
            "0",
            "module.cpp",
            "added",
            '+#include "header.h"\n+class MyClass {\n+public:\n+    void method();\n+};',
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()

        self.runner.run_benchmark(
            "C++ Regex Analysis",
            lambda: analyzer._extract_cpp_symbols(change),
            iterations=1000,
            language="cpp",
        )

    def bench_rust_analysis(self) -> None:
        """Benchmark Rust code analysis."""
        change = FileChange(
            "0",
            "lib.rs",
            "added",
            "+use std::collections::HashMap;\n+pub struct Data {\n+    items: HashMap<String, i32>,\n+}",
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()

        self.runner.run_benchmark(
            "Rust Regex Analysis",
            lambda: analyzer._extract_rust_symbols(change),
            iterations=1000,
            language="rust",
        )

    def bench_go_analysis(self) -> None:
        """Benchmark Go code analysis."""
        change = FileChange(
            "0",
            "main.go",
            "added",
            '+package main\n+import "fmt"\n+func process() {\n+    fmt.Println("hello")\n+}',
            ChangeStatus.UNKNOWN,
        )

        analyzer = DependencyAnalyzer()

        self.runner.run_benchmark(
            "Go Regex Analysis",
            lambda: analyzer._extract_go_symbols(change),
            iterations=1000,
            language="go",
        )

    def bench_mixed_language(self) -> None:
        """Benchmark analyzing mixed-language project."""
        changes = [
            FileChange(f"{i}", f"file{i}.py", "added", "+def func():\n+    pass")
            for i in range(10)
        ]
        changes.extend(
            [
                FileChange(f"{i+10}", f"file{i}.cpp", "added", "+void func() {}")
                for i in range(10)
            ]
        )

        analyzer = DependencyAnalyzer()

        self.runner.run_benchmark(
            "Mixed Language Analysis (20 files)",
            lambda: analyzer.analyze_file_dependencies(changes),
            iterations=100,
            file_count=20,
        )

    def bench_large_file_set(self) -> None:
        """Benchmark analyzing large number of files."""
        changes = [
            FileChange(f"{i}", f"file{i}.py", "added", "+def func():\n+    pass")
            for i in range(100)
        ]

        analyzer = DependencyAnalyzer()

        self.runner.run_benchmark(
            "Large File Set Analysis (100 files)",
            lambda: analyzer.analyze_file_dependencies(changes),
            iterations=50,
            file_count=100,
        )


class BinarySearchBenchmarks:
    """Benchmarks for binary search algorithms."""

    def __init__(self, runner: BenchmarkRunner) -> None:
        """Initialize binary search benchmarks.

        Args:
            runner: Benchmark runner to use.
        """
        self.runner = runner

    def run_all(self) -> None:
        """Run all binary search benchmarks."""
        self.bench_small_search_space()
        self.bench_medium_search_space()
        self.bench_large_search_space()
        self.bench_with_dependencies()

    def bench_small_search_space(self) -> None:
        """Benchmark binary search with small search space (8 items)."""

        class MockGit:
            def apply_changes(self, *args: Any, **kwargs: Any) -> bool:
                return True

            def checkout(self, *args: Any) -> None:
                pass

        class MockRunner:
            def __init__(self, bad_idx: int):
                self.bad_idx = bad_idx
                self.call_count = 0

            def run(self) -> CommandResult:
                # Simulate: if bad change is included, fail
                # For benchmarking, just cycle through results
                self.call_count += 1
                return CommandResult.FAIL if self.call_count % 3 == 0 else CommandResult.PASS

        changes = [
            FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}")
            for i in range(8)
        ]

        def run_bisect() -> None:
            engine = BifurcationEngine(MockGit(), MockRunner(3))  # type: ignore[arg-type]
            engine.bifurcate_files(changes, "base", verbose=False)

        self.runner.run_benchmark(
            "Binary Search (8 items)",
            run_bisect,
            iterations=500,
            search_space_size=8,
        )

    def bench_medium_search_space(self) -> None:
        """Benchmark binary search with medium search space (32 items)."""

        class MockGit:
            def apply_changes(self, *args: Any, **kwargs: Any) -> bool:
                return True

            def checkout(self, *args: Any) -> None:
                pass

        class MockRunner:
            def __init__(self):
                self.call_count = 0

            def run(self) -> CommandResult:
                self.call_count += 1
                return CommandResult.FAIL if self.call_count % 5 == 0 else CommandResult.PASS

        changes = [
            FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}")
            for i in range(32)
        ]

        def run_bisect() -> None:
            engine = BifurcationEngine(MockGit(), MockRunner())  # type: ignore[arg-type]
            engine.bifurcate_files(changes, "base", verbose=False)

        self.runner.run_benchmark(
            "Binary Search (32 items)",
            run_bisect,
            iterations=200,
            search_space_size=32,
        )

    def bench_large_search_space(self) -> None:
        """Benchmark binary search with large search space (128 items)."""

        class MockGit:
            def apply_changes(self, *args: Any, **kwargs: Any) -> bool:
                return True

            def checkout(self, *args: Any) -> None:
                pass

        class MockRunner:
            def __init__(self):
                self.call_count = 0

            def run(self) -> CommandResult:
                self.call_count += 1
                return CommandResult.FAIL if self.call_count % 7 == 0 else CommandResult.PASS

        changes = [
            FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}")
            for i in range(128)
        ]

        def run_bisect() -> None:
            engine = BifurcationEngine(MockGit(), MockRunner())  # type: ignore[arg-type]
            engine.bifurcate_files(changes, "base", verbose=False)

        self.runner.run_benchmark(
            "Binary Search (128 items)",
            run_bisect,
            iterations=50,
            search_space_size=128,
        )

    def bench_with_dependencies(self) -> None:
        """Benchmark binary search with dependency-aware optimization."""

        class MockGit:
            def apply_changes(self, *args: Any, **kwargs: Any) -> bool:
                return True

            def checkout(self, *args: Any) -> None:
                pass

        class MockRunner:
            def __init__(self):
                self.call_count = 0

            def run(self) -> CommandResult:
                self.call_count += 1
                return CommandResult.FAIL if self.call_count % 4 == 0 else CommandResult.PASS

        # Create changes with dependencies
        changes = [
            FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}", dependencies=[f"{i-1}"] if i > 0 else [])
            for i in range(16)
        ]

        def run_bisect() -> None:
            engine = BifurcationEngine(MockGit(), MockRunner())  # type: ignore[arg-type]
            engine.bifurcate_files(changes, "base", verbose=False)

        self.runner.run_benchmark(
            "Binary Search with Dependencies (16 items)",
            run_bisect,
            iterations=300,
            search_space_size=16,
            has_dependencies=True,
        )


class DependencyGraphBenchmarks:
    """Benchmarks for dependency graph operations."""

    def __init__(self, runner: BenchmarkRunner) -> None:
        """Initialize dependency graph benchmarks.

        Args:
            runner: Benchmark runner to use.
        """
        self.runner = runner

    def run_all(self) -> None:
        """Run all dependency graph benchmarks."""
        self.bench_graph_construction()
        self.bench_transitive_dependencies()
        self.bench_topological_sort()
        self.bench_independent_sets()

    def bench_graph_construction(self) -> None:
        """Benchmark dependency graph construction."""
        changes = [
            FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}", dependencies=[f"{i-1}"] if i > 0 else [])
            for i in range(50)
        ]

        self.runner.run_benchmark(
            "Dependency Graph Construction (50 nodes)",
            lambda: DependencyGraph(changes),
            iterations=500,
            node_count=50,
        )

    def bench_transitive_dependencies(self) -> None:
        """Benchmark transitive dependency resolution."""
        changes = [
            FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}", dependencies=[f"{i-1}"] if i > 0 else [])
            for i in range(50)
        ]

        graph = DependencyGraph(changes)

        self.runner.run_benchmark(
            "Transitive Dependency Resolution",
            lambda: graph.get_all_dependencies("49"),
            iterations=1000,
            chain_length=50,
        )

    def bench_topological_sort(self) -> None:
        """Benchmark topological sorting."""
        changes = [
            FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}", dependencies=[f"{i-1}"] if i > 0 else [])
            for i in range(100)
        ]

        graph = DependencyGraph(changes)

        self.runner.run_benchmark(
            "Topological Sort (100 nodes)",
            lambda: graph.topological_sort(),
            iterations=500,
            node_count=100,
        )

    def bench_independent_sets(self) -> None:
        """Benchmark finding independent sets."""
        # Create graph with multiple independent chains
        changes = []
        for chain in range(5):
            for i in range(20):
                idx = chain * 20 + i
                deps = [f"{chain * 20 + i - 1}"] if i > 0 else []
                changes.append(
                    FileChange(f"{idx}", f"file{idx}.py", "modified", f"diff{idx}", dependencies=deps)
                )

        graph = DependencyGraph(changes)

        self.runner.run_benchmark(
            "Find Independent Sets (100 nodes, 5 chains)",
            lambda: graph.get_independent_sets(),
            iterations=300,
            node_count=100,
            chain_count=5,
        )


class CacheBenchmarks:
    """Benchmarks for cache effectiveness."""

    def __init__(self, runner: BenchmarkRunner) -> None:
        """Initialize cache benchmarks.

        Args:
            runner: Benchmark runner to use.
        """
        self.runner = runner

    def run_all(self) -> None:
        """Run all cache benchmarks."""
        self.bench_cache_hits()
        self.bench_cache_miss()

    def bench_cache_hits(self) -> None:
        """Benchmark cache hit performance."""

        class MockGit:
            def apply_changes(self, *args: Any, **kwargs: Any) -> bool:
                return True

            def checkout(self, *args: Any) -> None:
                pass

        class MockRunner:
            def run(self) -> CommandResult:
                return CommandResult.PASS

        changes = [FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}") for i in range(10)]

        engine = BifurcationEngine(MockGit(), MockRunner())  # type: ignore[arg-type]

        # Prime the cache
        for i in range(10):
            engine._test_changes(changes, "base", [i])

        self.runner.run_benchmark(
            "Cache Hit Performance",
            lambda: engine._test_changes(changes, "base", [0]),
            iterations=10000,
        )

    def bench_cache_miss(self) -> None:
        """Benchmark cache miss (first access) performance."""

        class MockGit:
            def __init__(self):
                self.call_count = 0

            def apply_changes(self, *args: Any, **kwargs: Any) -> bool:
                self.call_count += 1
                return True

            def checkout(self, *args: Any) -> None:
                pass

        class MockRunner:
            def run(self) -> CommandResult:
                return CommandResult.PASS

        changes = [FileChange(f"{i}", f"file{i}.py", "modified", f"diff{i}") for i in range(100)]

        def test_new_combination() -> None:
            git = MockGit()
            runner = MockRunner()
            engine = BifurcationEngine(git, runner)  # type: ignore[arg-type]
            # Each call tests a different combination (cache miss)
            engine._test_changes(changes, "base", [git.call_count % 100])

        self.runner.run_benchmark(
            "Cache Miss Performance",
            test_new_combination,
            iterations=1000,
        )


def run_all_benchmarks() -> BenchmarkRunner:
    """Run all benchmark suites.

    Returns:
        BenchmarkRunner with all results.
    """
    runner = BenchmarkRunner()

    print("\nRunning Dependency Analysis Benchmarks...")
    dep_bench = DependencyAnalysisBenchmarks(runner)
    dep_bench.run_all()

    print("Running Binary Search Benchmarks...")
    search_bench = BinarySearchBenchmarks(runner)
    search_bench.run_all()

    print("Running Dependency Graph Benchmarks...")
    graph_bench = DependencyGraphBenchmarks(runner)
    graph_bench.run_all()

    print("Running Cache Benchmarks...")
    cache_bench = CacheBenchmarks(runner)
    cache_bench.run_all()

    return runner


if __name__ == "__main__":
    runner = run_all_benchmarks()
    runner.print_results()

    # Save results for regression tracking
    import sys
    from pathlib import Path

    if len(sys.argv) > 1:
        output_file = sys.argv[1]
    else:
        output_file = Path(__file__).parent / "benchmark_results.json"

    runner.save_results(str(output_file))
    print(f"Results saved to {output_file}")
