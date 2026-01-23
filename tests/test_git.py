import sys
import tempfile
import unittest
from pathlib import Path


class FakeRunner:
    def __init__(self):
        self.calls: list[tuple[list[str], bool]] = []

    def __call__(self, args: list[str], *, check: bool):
        self.calls.append((args, check))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from git import Git  # noqa: E402  pylint: disable=wrong-import-position


class GitTests(unittest.TestCase):
    def test_clone_with_submodules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / "org" / "repo"
            runner = FakeRunner()
            git = Git("https://example.com/repo.git", repo_dir, runner=runner)

            git.clone(with_submodules=True)

            self.assertTrue(repo_dir.exists())
            self.assertEqual(
                runner.calls,
                [
                    (
                        [
                            "git",
                            "clone",
                            "--recurse-submodules",
                            "--remote-submodules",
                            "https://example.com/repo.git",
                            str(repo_dir),
                        ],
                        True,
                    )
                ],
            )

    def test_clone_raises_if_directory_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / "existing"
            repo_dir.mkdir(parents=True)
            runner = FakeRunner()
            git = Git("https://example.com/repo.git", repo_dir, runner=runner)

            with self.assertRaises(FileExistsError):
                git.clone(with_submodules=False)

            self.assertEqual(runner.calls, [])

    def test_update_fetches_and_fast_forwards(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / "repo"
            repo_dir.mkdir()
            runner = FakeRunner()
            git = Git("https://example.com/repo.git", repo_dir, runner=runner)

            git.update()

            self.assertEqual(
                runner.calls,
                [
                    (
                        [
                            "git",
                            "-C",
                            str(repo_dir),
                            "fetch",
                            "--all",
                            "--prune",
                        ],
                        True,
                    ),
                    (
                        [
                            "git",
                            "-C",
                            str(repo_dir),
                            "merge",
                            "--ff-only",
                        ],
                        True,
                    ),
                ],
            )

    def test_switch_and_update_detaches_for_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / "repo"
            repo_dir.mkdir()
            runner = FakeRunner()
            git = Git("https://example.com/repo.git", repo_dir, runner=runner)

            git.switch_and_update("v1.2.3", is_tag=True)

            self.assertEqual(
                runner.calls,
                [
                    (
                        [
                            "git",
                            "-C",
                            str(repo_dir),
                            "fetch",
                            "--all",
                            "--prune",
                        ],
                        True,
                    ),
                    (
                        [
                            "git",
                            "-C",
                            str(repo_dir),
                            "switch",
                            "--detach",
                            "v1.2.3",
                        ],
                        True,
                    ),
                    (
                        [
                            "git",
                            "-C",
                            str(repo_dir),
                            "merge",
                            "--ff-only",
                        ],
                        True,
                    ),
                ],
            )


if __name__ == "__main__":
    unittest.main()
