"""Git repository wrapper module.

This module provides a Git class for performing common git operations
with a clean, Pythonic interface. It wraps git commands and provides
methods for cloning, updating, switching branches/tags, and running
custom commands within a repository.
"""

import os
import subprocess
from functools import partial
from pathlib import Path
from typing import Callable


class Git:
    """Wrapper for git operations with pluggable command execution."""

    def __init__(
        self,
        local_dir: Path,
        *,
        runner: Callable[..., None] | None = None,
    ) -> None:
        """Initialize a Git repository wrapper.

        Args:
            local_dir: The local directory path for the repository.
            runner: Optional callable to execute commands. Defaults
                    to subprocess.run with check=True.
        """
        self._local_dir = local_dir
        self._runner = runner or partial(subprocess.run, check=True)

    @property
    def local_dir(self):
        """Path where the local git repository is"""
        return self._local_dir

    def _git_run(self, cmd: list[str | Path]) -> subprocess.CompletedProcess | None:
        """Execute a git command in the repository.

        Args:
            cmd: Git command arguments (without 'git' prefix).
        """
        return self._runner(["git", "-C", self._local_dir, *cmd])

    def clone(self, repo_url: str, *, with_submodules: bool) -> None:
        """Clone the repository from the remote.

        Args:
            repo_url: The remote repository URL.
            with_submodules: If True, recursively clone submodules.

        Raises:
            FileExistsError: If the target directory already exists.
        """
        # prepare target directory
        if self._local_dir.exists():
            raise FileExistsError(
                f"Cannot clone {repo_url} because {self._local_dir} already exists"
            )
        self._local_dir.mkdir(parents=True, exist_ok=True)

        # execute cmd
        options = (
            ["--recurse-submodules", "--remote-submodules"] if with_submodules else []
        )
        self._runner(["git", "clone", *options, repo_url, self._local_dir])

    def _git_fetch(self) -> None:
        """Fetch all remote branches with pruning of deleted remote branches."""
        self._git_run(["fetch", "--all", "--prune", "--tags"])

    def _git_fast_forward(self) -> None:
        """Merge the current branch with fast-forward only."""
        self._git_run(["merge", "--ff-only"])

    def update(self) -> None:
        """Fetch updates and merge with the current branch."""
        self._git_fetch()
        self._git_fast_forward()

    def switch_and_update(self, branch_tag_name: str, *, is_tag: bool = False) -> None:
        """Switch to a branch or tag and update to match the remote.

        Args:
            branch_tag_name: The name of the branch or tag to switch to.
            is_tag: If True, detach HEAD at the tag; otherwise switch to the branch.
        """
        if is_tag:
            result = self._git_run(["tag", "--list", branch_tag_name])
            if result is None or 0 == len(result.stdout):
                # if tag does not exist locally we need to update. Otherwise we assume
                # that tags don't change so just use the existing one, its faster to not fetch
                self._git_fetch()
            self._git_run(["switch", "--detach", branch_tag_name])
        else:
            # got a branch
            self._git_fetch()
            self._git_run(["switch", branch_tag_name])
            self._git_fast_forward()

    def run(self, cmd: list[str]) -> subprocess.CompletedProcess | None:
        """Runs any command inside the repo_dir"""
        return self._runner(cmd, cwd=self._local_dir, check=True)


if __name__ == "__main__":
    REPO = "git@github.com:AFLplusplus/AFLplusplus.git"
    repo_dir = Path(__file__).resolve().parent.parent / "build" / "AFLplusolus"
    git = Git(repo_dir)
    if not repo_dir.is_dir():
        git.clone(REPO, with_submodules=False)
    git.switch_and_update("v4.35c", is_tag=True)
    # git.switch_and_update("stable")
    # build
    git.run(
        [
            "make",
            "PERFORMANCE=1",
            f"-j{os.cpu_count()}",
            "afl-fuzz",
            "afl-showmap",
            "afl-tmin",
            "afl-gotcpu",
            "afl-analyze",
            "afl-cmin",
        ]
    )
    git.run(["make", "PERFORMANCE=1", "-C", "utils/libdislocator"])
    git.run(["make", "PERFORMANCE=1", "-C", "utils/libtokencap"])
