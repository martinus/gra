# gra - Git Repo Admin

`gra` is a tiny clone helper. It keeps repositories under a flat root directory
and creates a normal Git checkout in a folder named after the remote's default
branch:

```text
~/git
└── gra
  ├── main
  └── wt
```

The default root is `~/git`. Configure a different root in `~/.gitconfig`:

```sh
git config --global gra.root ~/develop
```

# Installation

1. Clone `gra`.
  ```sh
  python3 -c "$(curl -fsLS https://raw.githubusercontent.com/martinus/gra/refs/heads/main/gra)" clone git@github.com:martinus/gra.git
  ```

2. Create a symlink in your path.
  ```sh
  ln -s ~/git/gra/main/gra ~/.local/bin/
  ```

# Commands

## clone - clone a remote repository

Clones one repository into `~/git/<name>/<default-branch>` and creates
`~/git/<name>/wt` for worktrees:

```sh
gra clone git@github.com:martinus/gra.git
```

This creates:

```text
~/git/gra
├── main
└── wt
```

The local repository name is derived from the URL. If that name already exists,
`gra` exits with an error and suggests using `--name`:

```sh
gra clone git@github.com:martinus/AFLplusplus.git --name AFLplusplus-martinus
```

By default, submodules are cloned recursively. Use `--no-submodules` to skip
submodules:

```sh
gra clone git@github.com:martinus/gra.git --no-submodules
```

`gra` also adds `.claude/worktrees/` to the checkout's local Git exclude file so
Claude Code worktrees do not show up as untracked files.

## ls - list repositories and worktrees

Run `gra ls` from anywhere to see all repositories under the configured gra root
and every worktree Git knows about:

```sh
gra ls
```

Example output:

```text
Root: /home/me/git
Repositories: 1  Worktrees: 2

REPOSITORY  WORKTREE   REF      STATUS   REMOTE
gra         main       main     ✓ clean  git@github.com:martinus/gra
            wt/review  feature  ● dirty
```

## clean - report or remove safe worktrees

Run `gra clean` from anywhere to classify every worktree under the configured
gra root. It prints one table like `gra ls`, with `VERDICT` and `REASON`
columns added:

```sh
gra clean
```

Example output:

```text
Root: /home/me/git
Repositories: 2  Worktrees: 4

REPOSITORY  WORKTREE    REF      STATUS     VERDICT  REASON
gra         main        main     ✓ clean    keep     default checkout
            wt/review   feature  ● dirty    keep     uncommitted changes
tools       main        main     ✓ clean    keep     default checkout
            wt/old-fix  old-fix  ✓ clean    safe     merged into origin/main

Dry run. Re-run with --yes to remove 1 worktree(s).
```

Verdicts mean:

* `keep` - the worktree is the default checkout, has uncommitted changes, or
  has commits that are not merged into origin's default branch.
* `safe` - the worktree is clean and its `HEAD` is already merged into origin's
  default branch.
* `prune` - Git still knows about the worktree, but the directory no longer
  exists on disk.

By default, `gra clean` is a dry run. Use `--yes` to remove `safe` worktrees and
prune missing entries:

```sh
gra clean --yes
```

Before classifying, `gra clean` runs `git fetch --prune origin` in each
repository. Use `--no-fetch` to skip that step:

```sh
gra clean --no-fetch
```

`gra clean --yes` deletes local branches with `git branch -d` only after the
worktree was removed. It never deletes the default checkout, never removes dirty
worktrees, and never forces branch deletion with `-D`.

## cd - jump to a worktree

Run `gra cd` to choose any worktree under the gra root with `fzf`:

```sh
gra cd
```

The command prints the selected path. To make `gra cd` change the current Bash
shell's directory, add this to `~/.bashrc` after `gra` is on your `PATH`:

```sh
eval "$(gra shell bash)"
```

Then run `gra cd`, select a worktree, and press Enter.

## code - open a worktree in Visual Studio Code

Run `gra code` to choose any worktree under the gra root with the same `fzf`
picker as `gra cd`, then open the selected directory in Visual Studio Code:

```sh
gra code
```

Pass an SSH target to choose from that machine's gra worktrees and open the
selected folder with VS Code Remote SSH. The target can include a username:

```sh
gra code martinleitnerankerl@10.102.7.17
```

This expects `gra` to be installed on the remote host. `gra code` adds
`~/.local/bin` to the remote `PATH` before invoking `gra`, so the usual symlink
location works for non-interactive SSH sessions.

When using `~/.ssh/config`, put the username in `User`, not in the `Host`
pattern, then pass the `Host` value to `gra code`. This avoids VS Code Remote
SSH combining the username twice:

```sshconfig
Host 10.102.7.17
  HostName 10.102.7.17
  User martinleitnerankerl
```

```sh
gra code 10.102.7.17
```

## wt - create or update worktrees

Run `gra wt BRANCH` from a checkout, worktree, the repo folder, or the `wt`
folder to create a worktree for an existing branch. The folder name under `wt`
is derived from the branch name:

```sh
gra wt feature/search
```

This creates `~/git/gra/wt/feature-search` and checks out `feature/search`.

Use `--name` for a reusable worktree folder. This is useful for a review slot
that moves between branches:

```sh
gra wt --name review feature/search
gra wt --name review bugfix/crash
```

Named worktrees check out the requested branch. If the branch only exists as
`origin/<branch>`, `gra` creates a local tracking branch. Git allows a branch to
be checked out in only one worktree at a time, so switching `review` to a branch
that is already checked out elsewhere will fail with Git's normal message.

If the branch does not exist locally or on `origin`, `gra` asks whether it
should create the branch from origin's default branch, for example `origin/main`,
`origin/master`, or the remote `HEAD` branch.


# Development

Install test dependencies and run the suite with:

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```


# Alternatives

* [ghq](https://github.com/x-motemen/ghq) was the main inspiration for `gra`. gra is much simpler,
  a single python file, git only, and integrates easily with VSCode.
* [ghr](https://github.com/siketyan/ghr) is another ghq clone, written in Rust, but it currently
  did not work with non github URLs. I like the bash integration.
* [rhq](https://github.com/ubnt-intrepid/rhq) Another one in rust
* [projj](https://github.com/popomore/projj)
