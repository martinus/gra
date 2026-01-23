import os
import subprocess
from functools import partial, wraps
from pathlib import Path
import time
from typing import Callable


def debug_timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        before = time.perf_counter()
        result = func(*args, **kwargs)
        after = time.perf_counter()
        print(f"{after - before:.4f}s | {func.__name__}")
        return result

    return wrapper


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
            runner: Optional callable to execute commands. Defaults to subprocess.run with check=True.
        """
        self._local_dir = local_dir
        self._runner = runner or partial(subprocess.run, check=True)

    @property
    def dir(self):
        return self._local_dir

    def _git_run(self, cmd: list[str | Path]) -> None:
        """Execute a git command in the repository.

        Args:
            cmd: Git command arguments (without 'git' prefix).
        """
        self._runner(["git", "-C", self._local_dir, *cmd])

    @debug_timer
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

    @debug_timer
    def _git_fetch(self) -> None:
        """Fetch all remote branches with pruning of deleted remote branches."""
        self._git_run(["fetch", "--all", "--prune", "--tags"])

    @debug_timer
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
        options = ["--detach"] if is_tag else []
        self._git_fetch()
        self._git_run(["switch", *options, branch_tag_name])
        if not is_tag:
            self._git_fast_forward()

    def run(self, cmd: list[str]) -> subprocess.CompletedProcess[bytes] | None:
        """Runs any command inside the repo_dir"""
        return self._runner(cmd, cwd=self._local_dir, check=True)


if __name__ == "__main__":
    repo = "git@github.com:AFLplusplus/AFLplusplus.git"
    repo_dir = Path(__file__).resolve().parent.parent / "build" / "AFLplusolus"
    git = Git(repo_dir)
    if not repo_dir.is_dir():
        git.clone(repo, with_submodules=False)
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
