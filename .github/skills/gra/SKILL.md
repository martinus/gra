---
name: gra
description: 'Use when working with gra, the Git Repo Admin CLI: clone repositories, list or open worktrees, create reusable worktrees, clean merged worktrees, inspect gra root layout, or explain gra commands.'
argument-hint: 'gra task or command'
---

# gra Usage

`gra` manages a flat Git workspace rooted at `git config gra.root` or `~/git`:

```text
~/git/<repo>/<default-branch>
~/git/<repo>/wt/<worktree>
```

## Commands

- `gra clone URL [--name NAME] [--no-submodules]` clones into the gra layout.
- `gra ls` lists all repositories and worktrees under the gra root.
- `gra wt BRANCH [--name NAME]` creates or reuses a worktree under `<repo>/wt`; run it from a checkout, worktree, repo folder, or `wt` folder.
- `gra clean [--no-fetch]` dry-runs cleanup across all repositories, adding `VERDICT` and `REASON` columns to the `gra ls` table shape.
- `gra clean --yes` removes `remove` worktrees and prunes `missing` worktree entries.
- `gra cd` uses `fzf` to print a selected local worktree path.
- `gra code [SSH_TARGET]` uses `fzf` to open a local or remote worktree in VS Code.
- `gra shell bash` prints shell integration so `gra cd` can change the current Bash directory.

## Cleanup Safety

For cleanup tasks, run `gra clean` first and explain the table before applying changes.

- `keep`: default checkout, dirty worktree, unknown default branch, or commits not merged into origin's default branch.
- `remove`: clean worktree whose `HEAD` is merged or patch-equivalent in origin's default branch.
- `prune`: Git knows about the worktree, but the directory is missing.

Use `gra clean --yes` only when the user explicitly wants cleanup applied. It never removes the default checkout, never removes dirty worktrees, and deletes local branches only with safe `git branch -d`.

## Notes

- Use `--name` for reusable review worktrees, for example `gra wt --name review feature/foo`.
- If a branch exists only on `origin`, `gra wt` creates a local tracking branch.
- If a branch is missing locally and remotely, `gra wt` asks before creating it from origin's default branch.