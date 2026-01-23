from functools import partial
from pathlib import Path
import subprocess
from typing import Callable


class Git:
    def __init__(
        self, repo_url: str, local_dir: Path, runner: Callable[..., None] | None = None
    ):
        self._repo_url = repo_url
        self._local_dir = local_dir
        self._runner = runner or partial(subprocess.run, check=True)

    def _git_run(self, cmd: list[str]):
        self._runner(["git", "-C", self._local_dir, *cmd], check=True)

    def clone(self, with_submodules: bool):
        # prepare target directory
        if self._local_dir.exists():
            raise FileExistsError(
                f"Cannot clone {self._repo_url} because {self._local_dir} already exists"
            )
        self._local_dir.mkdir(parents=True, exist_ok=True)

        # execute cmd
        options = (
            ["--recurse-submodules", "--remote-submodules"] if with_submodules else []
        )
        self._runner(
            ["git", "clone", *options, self._repo_url, self._local_dir], check=True
        )

    def _git_fetch(self):
        # Adding --prune is highly recommended. it deletes the local "ghost"
        # branches that have been deleted on the server, keeping your git branch -a
        # output clean.
        self._git_run(["fetch", "--all", "--prune"])

    def _git_fast_forward(self):
        self._git_run(["merge", "--ff-only"])

    def update(self):
        self._git_fetch()
        self._git_fast_forward()

    def switch_and_update(self, branch_tag_name: str, is_tag: bool = False):
        """Switches to a different branch/tag and updates to match the remote"""
        options = ["--detach"] if is_tag else []
        self._git_fetch()
        self._git_run(["switch", *options, branch_tag_name])
        self._git_fast_forward()
