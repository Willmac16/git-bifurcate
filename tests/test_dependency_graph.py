"""Tests for dependency graph management."""

from __future__ import annotations

from git_bifurcate.dependency_graph import DependencyGraph, build_dependency_graph
from git_bifurcate.models import FileChange, HunkChange


class TestDependencyGraph:
    """Tests for DependencyGraph class."""

    def test_simple_dependency_chain(self) -> None:
        """Test building graph with simple A->B->C chain."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["1"]),
        ]

        graph = DependencyGraph(changes)

        assert graph.graph["0"] == set()
        assert graph.graph["1"] == {"0"}
        assert graph.graph["2"] == {"1"}

    def test_get_all_dependencies(self) -> None:
        """Test getting transitive dependencies."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["1"]),
        ]

        graph = DependencyGraph(changes)

        # C depends on B which depends on A
        deps = graph.get_all_dependencies("2")
        assert deps == {"0", "1"}

        deps = graph.get_all_dependencies("1")
        assert deps == {"0"}

        deps = graph.get_all_dependencies("0")
        assert deps == set()

    def test_get_all_dependents(self) -> None:
        """Test getting all dependents (reverse dependencies)."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["0"]),
        ]

        graph = DependencyGraph(changes)

        # A is depended on by both B and C
        dependents = graph.get_all_dependents("0")
        assert dependents == {"1", "2"}

        dependents = graph.get_all_dependents("1")
        assert dependents == set()

    def test_expand_with_dependencies(self) -> None:
        """Test expanding change list to include dependencies."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["1"]),
        ]

        graph = DependencyGraph(changes)

        # Testing just C should include A and B
        expanded = graph.expand_with_dependencies([2])
        assert set(expanded) == {0, 1, 2}

        # Testing B should include A
        expanded = graph.expand_with_dependencies([1])
        assert set(expanded) == {0, 1}

    def test_topological_sort(self) -> None:
        """Test topological sorting of dependency graph."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["1"]),
        ]

        graph = DependencyGraph(changes)
        sorted_indices = graph.topological_sort()

        assert sorted_indices is not None
        # A should come before B, B before C
        assert sorted_indices.index(0) < sorted_indices.index(1)
        assert sorted_indices.index(1) < sorted_indices.index(2)

    def test_circular_dependency_detection(self) -> None:
        """Test detecting circular dependencies."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=["1"]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
        ]

        graph = DependencyGraph(changes)

        assert graph.has_cycle() is True
        assert graph.topological_sort() is None

    def test_no_cycle(self) -> None:
        """Test graph without cycles."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
        ]

        graph = DependencyGraph(changes)

        assert graph.has_cycle() is False
        assert graph.topological_sort() is not None

    def test_get_root_changes(self) -> None:
        """Test identifying root changes (no dependencies)."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=[]),
        ]

        graph = DependencyGraph(changes)
        roots = graph.get_root_changes()

        assert set(roots) == {0, 2}

    def test_get_leaf_changes(self) -> None:
        """Test identifying leaf changes (nothing depends on them)."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["1"]),
        ]

        graph = DependencyGraph(changes)
        leaves = graph.get_leaf_changes()

        assert leaves == [2]

    def test_independent_sets(self) -> None:
        """Test identifying independent sets of changes."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=[]),
            FileChange("3", "d.py", "added", "diff3", dependencies=["2"]),
        ]

        graph = DependencyGraph(changes)
        sets = graph.get_independent_sets()

        # Should have two independent sets: {0,1} and {2,3}
        assert len(sets) == 2
        assert {0, 1} in [set(s) for s in sets]
        assert {2, 3} in [set(s) for s in sets]

    def test_can_test_separately(self) -> None:
        """Test checking if two sets can be tested independently."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=[]),
        ]

        graph = DependencyGraph(changes)

        # 0 and 1 are dependent, can't test separately
        assert graph.can_test_separately([0], [1]) is False
        assert graph.can_test_separately([1], [0]) is False

        # 1 and 2 are independent
        assert graph.can_test_separately([1], [2]) is True
        assert graph.can_test_separately([2], [1]) is True

    def test_get_dependency_depth(self) -> None:
        """Test calculating dependency depth."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["1"]),
        ]

        graph = DependencyGraph(changes)

        assert graph.get_dependency_depth("0") == 0
        assert graph.get_dependency_depth("1") == 1
        assert graph.get_dependency_depth("2") == 2

    def test_get_stats(self) -> None:
        """Test getting graph statistics."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=[]),
        ]

        graph = DependencyGraph(changes)
        stats = graph.get_stats()

        assert stats["total_changes"] == 3
        assert stats["total_dependencies"] == 1
        assert stats["changes_with_dependencies"] == 1
        assert stats["root_changes"] == 2
        assert stats["leaf_changes"] == 2
        assert stats["has_cycle"] is False

    def test_diamond_dependency(self) -> None:
        """Test diamond dependency pattern: A->B, A->C, B->D, C->D."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["0"]),
            FileChange("3", "d.py", "added", "diff3", dependencies=["1", "2"]),
        ]

        graph = DependencyGraph(changes)

        # D depends on A transitively through both B and C
        deps = graph.get_all_dependencies("3")
        assert deps == {"0", "1", "2"}

        # Testing D should include all dependencies
        expanded = graph.expand_with_dependencies([3])
        assert set(expanded) == {0, 1, 2, 3}

    def test_minimal_testable_subset(self) -> None:
        """Test finding minimal testable subset."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["1"]),
            FileChange("3", "d.py", "added", "diff3", dependencies=[]),
        ]

        graph = DependencyGraph(changes)

        # To test C, need A and B
        minimal = graph.minimal_testable_subset([2])
        assert set(minimal) == {0, 1, 2}

        # To test D, only need D
        minimal = graph.minimal_testable_subset([3])
        assert set(minimal) == {3}


class TestDependencyGraphWithHunks:
    """Tests for DependencyGraph with HunkChange objects."""

    def test_hunk_dependencies(self) -> None:
        """Test dependency graph with hunks."""
        hunks = [
            HunkChange("0", "f.py", 1, 5, 1, 3, 1, 5, "diff0", dependencies=[]),
            HunkChange("1", "f.py", 10, 15, 10, 3, 10, 5, "diff1", dependencies=["0"]),
        ]

        graph = DependencyGraph(hunks)

        assert graph.graph["0"] == set()
        assert graph.graph["1"] == {"0"}

    def test_expand_hunk_dependencies(self) -> None:
        """Test expanding hunk indices with dependencies."""
        hunks = [
            HunkChange("0", "f.py", 1, 5, 1, 3, 1, 5, "diff0", dependencies=[]),
            HunkChange("1", "f.py", 10, 15, 10, 3, 10, 5, "diff1", dependencies=["0"]),
            HunkChange("2", "f.py", 20, 25, 20, 3, 20, 5, "diff2", dependencies=["1"]),
        ]

        graph = DependencyGraph(hunks)
        expanded = graph.expand_with_dependencies([2])

        # Should include all hunks in the chain
        assert set(expanded) == {0, 1, 2}


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph helper function."""

    def test_build_from_file_changes(self) -> None:
        """Test building graph from file changes."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
        ]

        graph = build_dependency_graph(changes)

        assert isinstance(graph, DependencyGraph)
        assert graph.graph["1"] == {"0"}

    def test_build_from_hunk_changes(self) -> None:
        """Test building graph from hunk changes."""
        hunks = [
            HunkChange("0", "f.py", 1, 5, 1, 3, 1, 5, "diff0", dependencies=[]),
            HunkChange("1", "f.py", 10, 15, 10, 3, 10, 5, "diff1", dependencies=["0"]),
        ]

        graph = build_dependency_graph(hunks)

        assert isinstance(graph, DependencyGraph)
        assert graph.graph["1"] == {"0"}


class TestComplexScenarios:
    """Tests for complex dependency scenarios."""

    def test_multiple_roots(self) -> None:
        """Test graph with multiple root nodes."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=[]),
            FileChange("2", "c.py", "added", "diff2", dependencies=[]),
            FileChange("3", "d.py", "added", "diff3", dependencies=["0", "1", "2"]),
        ]

        graph = DependencyGraph(changes)
        roots = graph.get_root_changes()

        assert set(roots) == {0, 1, 2}

        # D depends on all roots
        deps = graph.get_all_dependencies("3")
        assert deps == {"0", "1", "2"}

    def test_complex_transitive_dependencies(self) -> None:
        """Test complex transitive dependency resolution."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["0"]),
            FileChange("3", "d.py", "added", "diff3", dependencies=["1", "2"]),
            FileChange("4", "e.py", "added", "diff4", dependencies=["3"]),
        ]

        graph = DependencyGraph(changes)

        # E depends on everything
        deps = graph.get_all_dependencies("4")
        assert deps == {"0", "1", "2", "3"}

        # Expanded test for E includes all
        expanded = graph.expand_with_dependencies([4])
        assert set(expanded) == {0, 1, 2, 3, 4}

    def test_independent_components(self) -> None:
        """Test graph with completely independent components."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=[]),
            FileChange("3", "d.py", "added", "diff3", dependencies=["2"]),
            FileChange("4", "e.py", "added", "diff4", dependencies=[]),
        ]

        graph = DependencyGraph(changes)
        sets = graph.get_independent_sets()

        # Should have 3 independent components
        assert len(sets) == 3

        # Verify independence
        assert graph.can_test_separately([0, 1], [2, 3]) is True
        assert graph.can_test_separately([0, 1], [4]) is True
        assert graph.can_test_separately([2, 3], [4]) is True

    def test_self_loop_prevention(self) -> None:
        """Test that self-loops are handled correctly."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=["0"]),  # Self-loop
        ]

        graph = DependencyGraph(changes)

        # Self-loop creates a cycle
        assert graph.has_cycle() is True

    def test_empty_graph(self) -> None:
        """Test empty dependency graph."""
        changes: list[FileChange | HunkChange] = []

        graph = DependencyGraph(changes)
        stats = graph.get_stats()

        assert stats["total_changes"] == 0
        assert stats["total_dependencies"] == 0
        assert stats["has_cycle"] is False

    def test_single_change_graph(self) -> None:
        """Test graph with single change."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
        ]

        graph = DependencyGraph(changes)

        assert graph.get_root_changes() == [0]
        assert graph.get_leaf_changes() == [0]
        assert graph.get_all_dependencies("0") == set()
        assert graph.has_cycle() is False

    def test_dependency_on_nonexistent_change(self) -> None:
        """Test handling of dependencies on non-existent changes."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0", "999"]),
        ]

        graph = DependencyGraph(changes)

        # Should handle non-existent dependency gracefully
        assert "0" in graph.graph["1"]
        # Non-existent dependency might be in graph or filtered out
        deps = graph.get_all_dependencies("1")
        assert "0" in deps

    def test_get_all_dependents_with_multiple_paths(self) -> None:
        """Test get_all_dependents with multiple paths to same node."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
            FileChange("1", "b.py", "added", "diff1", dependencies=["0"]),
            FileChange("2", "c.py", "added", "diff2", dependencies=["0"]),
            FileChange("3", "d.py", "added", "diff3", dependencies=["1", "2"]),
        ]

        graph = DependencyGraph(changes)

        # 0 is depended on by 1, 2, and transitively by 3
        dependents = graph.get_all_dependents("0")
        assert dependents == {"1", "2", "3"}

    def test_get_dependency_depth_nonexistent(self) -> None:
        """Test dependency depth for non-existent change."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", dependencies=[]),
        ]

        graph = DependencyGraph(changes)

        # Non-existent change should have depth 0
        depth = graph.get_dependency_depth("999")
        assert depth == 0
