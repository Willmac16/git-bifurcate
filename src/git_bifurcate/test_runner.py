"""Test execution for bifurcation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from git_bifurcate.models import CommandResult


class CommandRunner:
    """Runs test commands and captures results."""

    def __init__(
        self, test_command: str, working_dir: Path | str | None = None, timeout: int = 300
    ) -> None:
        """Initialize test runner.

        Args:
            test_command: Shell command to run tests.
            working_dir: Directory to run tests in. Defaults to current directory.
            timeout: Timeout in seconds for test execution.
        """
        self.test_command = test_command
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.timeout = timeout

    def run(self) -> CommandResult:
        """Run the test command.

        Returns:
            CommandResult indicating outcome.
        """
        try:
            result = subprocess.run(
                self.test_command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

            if result.returncode == 0:
                return CommandResult.PASS
            else:
                return CommandResult.FAIL

        except subprocess.TimeoutExpired:
            return CommandResult.ERROR
        except Exception:
            return CommandResult.ERROR
