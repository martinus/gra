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

## cd - jump to a worktree

Run `gra cd` to choose any worktree under the gra root with `fzf`:

```sh
gra cd
```

The command prints the selected path. To make `gra cd` change the current Bash
shell's directory, add this to `~/.bashrc` after `gra` is on your `PATH`:

```sh
eval "$(gra init bash)"
```

Then run `gra cd`, select a worktree, and press Enter.

## wt - list, create, or update worktrees

Run `gra wt` from a checkout, worktree, the repo folder, or the `wt` folder to
see the repo's worktrees and their status:

```sh
gra wt
```

Create a worktree for an existing branch by passing the branch name. The folder
name under `wt` is derived from the branch name:

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


# Alternatives

* [ghq](https://github.com/x-motemen/ghq) was the main inspiration for `gra`. gra is much simpler,
  a single python file, git only, and integrates easily with VSCode.
* [ghr](https://github.com/siketyan/ghr) is another ghq clone, written in Rust, but it currently
  did not work with non github URLs. I like the bash integration.
* [rhq](https://github.com/ubnt-intrepid/rhq) Another one in rust
* [projj](https://github.com/popomore/projj)
