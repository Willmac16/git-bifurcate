"""Dependency graph management for change dependencies.

This module provides utilities for building and working with dependency graphs
to optimize bifurcation and handle dependencies efficiently.
"""

from __future__ import annotations

from collections import deque
from typing import TypeVar

from git_bifurcate.models import FileChange, HunkChange

T = TypeVar("T", FileChange, HunkChange)


class DependencyGraph:
    """Represents a dependency graph for changes."""

    def __init__(self, changes: list[T]) -> None:
        """Initialize dependency graph.

        Args:
            changes: List of changes with dependency information.
        """
        self.changes = changes
        self.graph: dict[str, set[str]] = {}  # change_id -> set of dependency ids
        self.reverse_graph: dict[str, set[str]] = {}  # dependency_id -> set of dependent ids

        self._build_graph()

    def _build_graph(self) -> None:
        """Build the dependency graph from changes."""
        # Initialize
        for change in self.changes:
            self.graph[change.id] = set(change.dependencies)
            self.reverse_graph[change.id] = set()

        # Build reverse graph
        for change_id, deps in self.graph.items():
            for dep_id in deps:
                if dep_id not in self.reverse_graph:
                    self.reverse_graph[dep_id] = set()
                self.reverse_graph[dep_id].add(change_id)

    def get_all_dependencies(self, change_id: str) -> set[str]:
        """Get all transitive dependencies for a change.

        Args:
            change_id: ID of the change.

        Returns:
            Set of all dependency IDs (including transitive).
        """
        visited = set()
        queue = deque([change_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue

            visited.add(current)
            deps = self.graph.get(current, set())
            queue.extend(deps - visited)

        # Remove the original change from the result
        visited.discard(change_id)
        return visited

    def get_all_dependents(self, change_id: str) -> set[str]:
        """Get all changes that depend on this change (directly or transitively).

        Args:
            change_id: ID of the change.

        Returns:
            Set of all dependent change IDs.
        """
        visited = set()
        queue = deque([change_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue

            visited.add(current)
            dependents = self.reverse_graph.get(current, set())
            queue.extend(dependents - visited)

        # Remove the original change from the result
        visited.discard(change_id)
        return visited

    def expand_with_dependencies(self, change_indices: list[int]) -> list[int]:
        """Expand a list of change indices to include all their dependencies.

        Args:
            change_indices: List of change indices to test.

        Returns:
            Expanded list including all required dependencies.
        """
        change_ids = {self.changes[i].id for i in change_indices}
        all_ids = change_ids.copy()

        # For each change, add all its dependencies
        for idx in change_indices:
            change_id = self.changes[idx].id
            deps = self.get_all_dependencies(change_id)
            all_ids.update(deps)

        # Convert back to indices
        id_to_idx = {change.id: i for i, change in enumerate(self.changes)}
        return sorted(id_to_idx[cid] for cid in all_ids if cid in id_to_idx)

    def get_independent_sets(self) -> list[list[int]]:
        """Identify independent sets of changes that can be tested separately.

        Returns:
            List of lists, where each inner list is a set of change indices
            that must be tested together.
        """
        # Find strongly connected components (for circular dependencies)
        visited = set()
        components: list[list[int]] = []
        id_to_idx = {change.id: i for i, change in enumerate(self.changes)}

        def dfs(change_id: str, component: set[str]) -> None:
            if change_id in visited:
                return

            visited.add(change_id)
            component.add(change_id)

            # Visit dependencies and dependents (bidirectional)
            for dep in self.graph.get(change_id, set()):
                dfs(dep, component)
            for dependent in self.reverse_graph.get(change_id, set()):
                dfs(dependent, component)

        for change in self.changes:
            if change.id not in visited:
                component: set[str] = set()
                dfs(change.id, component)
                component_indices = [id_to_idx[cid] for cid in component if cid in id_to_idx]
                components.append(sorted(component_indices))

        return components

    def topological_sort(self) -> list[int] | None:
        """Perform topological sort on the dependency graph.

        Returns:
            List of change indices in topological order, or None if there's a cycle.
        """
        in_degree = {change.id: 0 for change in self.changes}

        # Calculate in-degrees
        for change_id, deps in self.graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[change_id] += 1

        # Find all nodes with in-degree 0
        queue = deque([cid for cid, degree in in_degree.items() if degree == 0])
        sorted_ids: list[str] = []

        while queue:
            current = queue.popleft()
            sorted_ids.append(current)

            # Reduce in-degree for dependents
            for dependent in self.reverse_graph.get(current, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # Check for cycle
        if len(sorted_ids) != len(self.changes):
            return None

        # Convert to indices
        id_to_idx = {change.id: i for i, change in enumerate(self.changes)}
        return [id_to_idx[cid] for cid in sorted_ids if cid in id_to_idx]

    def has_cycle(self) -> bool:
        """Check if the dependency graph has a cycle.

        Returns:
            True if there's a circular dependency, False otherwise.
        """
        return self.topological_sort() is None

    def get_root_changes(self) -> list[int]:
        """Get changes that have no dependencies (roots of the graph).

        Returns:
            List of indices for root changes.
        """
        roots = []
        for i, change in enumerate(self.changes):
            if not self.graph.get(change.id, set()):
                roots.append(i)
        return roots

    def get_leaf_changes(self) -> list[int]:
        """Get changes that nothing depends on (leaves of the graph).

        Returns:
            List of indices for leaf changes.
        """
        leaves = []
        for i, change in enumerate(self.changes):
            if not self.reverse_graph.get(change.id, set()):
                leaves.append(i)
        return leaves

    def minimal_testable_subset(self, target_indices: list[int]) -> list[int]:
        """Find the minimal set of changes needed to test the target changes.

        This includes the targets and all their transitive dependencies.

        Args:
            target_indices: Indices of changes we want to test.

        Returns:
            Minimal list of indices including all dependencies.
        """
        return self.expand_with_dependencies(target_indices)

    def can_test_separately(self, indices1: list[int], indices2: list[int]) -> bool:
        """Check if two sets of changes can be tested independently.

        Args:
            indices1: First set of change indices.
            indices2: Second set of change indices.

        Returns:
            True if the sets are independent, False if they have dependencies.
        """
        ids1 = {self.changes[i].id for i in indices1}
        ids2 = {self.changes[i].id for i in indices2}

        # Check if any change in set1 depends on set2 or vice versa
        for cid in ids1:
            deps = self.get_all_dependencies(cid)
            if deps & ids2:
                return False

        for cid in ids2:
            deps = self.get_all_dependencies(cid)
            if deps & ids1:
                return False

        return True

    def get_dependency_depth(self, change_id: str) -> int:
        """Get the maximum depth of dependencies for a change.

        Args:
            change_id: ID of the change.

        Returns:
            Maximum dependency depth (0 if no dependencies).
        """
        if change_id not in self.graph:
            return 0

        deps = self.graph[change_id]
        if not deps:
            return 0

        return 1 + max(self.get_dependency_depth(dep) for dep in deps)

    def get_stats(self) -> dict[str, int]:
        """Get statistics about the dependency graph.

        Returns:
            Dictionary with graph statistics.
        """
        total_deps = sum(len(deps) for deps in self.graph.values())
        has_deps = sum(1 for deps in self.graph.values() if deps)

        return {
            "total_changes": len(self.changes),
            "total_dependencies": total_deps,
            "changes_with_dependencies": has_deps,
            "root_changes": len(self.get_root_changes()),
            "leaf_changes": len(self.get_leaf_changes()),
            "has_cycle": self.has_cycle(),
            "independent_sets": len(self.get_independent_sets()),
        }


def build_dependency_graph[T: (FileChange, HunkChange)](changes: list[T]) -> DependencyGraph:
    """Build a dependency graph from a list of changes.

    Args:
        changes: List of FileChange or HunkChange objects with dependency info.

    Returns:
        DependencyGraph object.
    """
    return DependencyGraph(changes)
