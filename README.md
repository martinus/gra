# gra - Git Repo Admin

`gra` is a tiny worktree-first clone helper. It keeps repositories under a flat
root directory as bare checkouts, and all work happens in short-named worktrees
next to them:

```text
~/gra
└── martinus-oans
  ├── .bare
  ├── hare
  └── rose
```

There is no default checkout: no branch is ever pinned by a checkout you do not
use, so any worktree can be on `main`, rebase onto it, or switch to any branch
freely.

Worktree names are short random words (`hare`, `rose`, `wolf`, ...), all four
letters, unique across **all** repositories, and unrelated to the branch they
have checked out. A worktree is just a workspace: create one with `gra start`,
switch branches inside it with `gra switch`, and throw it away with `gra done`.
Because names are globally unique, a word like `wolf` identifies one worktree
across the whole machine - in `gra cd wolf`, in tmux window names, and in
conversation.

The default root is `~/gra`. Configure a different root in `~/.gitconfig`:

```sh
git config --global gra.root ~/develop
```

# Installation

1. Clone `gra`.
  ```sh
  python3 -c "$(curl -fsLS https://raw.githubusercontent.com/martinus/gra/refs/heads/main/gra)" clone git@github.com:martinus/gra.git
  ```

2. Create a worktree and symlink the script from it into your path:
  ```sh
  cd ~/gra/martinus-gra
  python3 -c "$(curl -fsLS https://raw.githubusercontent.com/martinus/gra/refs/heads/main/gra)" start main --no-tmux
  ln -s ~/gra/martinus-gra/*/gra ~/.local/bin/
  ```

3. Optional but recommended: enable the shell integration in `~/.bashrc` so
  `gra cd` changes directories and `gra done` leaves the removed directory:
  ```sh
  eval "$(gra shell bash)"
  ```

# Commands

## clone - clone a remote repository

Clones one repository as a bare checkout into `~/gra/<owner>-<repo>/.bare`:

```sh
gra clone git@github.com:martinus/oans.git
```

This creates:

```text
~/gra/martinus-oans
└── .bare
```

No branch is checked out; use `gra start` to begin working. The local name is
`<owner>-<repo>` for remote URLs and the repository name for local paths. Use
`--name` to override it:

```sh
gra clone git@github.com:martinus/AFLplusplus.git --name AFLplusplus-martinus
```

The bare checkout is set up to behave like a normal clone:

* the fetch refspec tracks all of origin's branches as `origin/<branch>`
  remote-tracking refs, and never mirrors them into local branches,
* `origin/HEAD` points at origin's default branch,
* reflogs are enabled (bare repositories disable them by default),
* `.claude/worktrees/` and `.grakeep` are added to the shared local Git
  exclude file so tool-managed paths and keep markers do not show up as
  untracked files in any worktree.

## start - create a new worktree

Run `gra start` from anywhere inside a repository under the gra root. It picks
a random unused four-letter word and creates a worktree with that name next to
`.bare`:

```sh
gra start feature/search
```

```text
~/gra/martinus-oans
├── .bare
└── hare        <- checked out feature/search
```

With a branch, `gra start` checks it out. If the branch only exists as
`origin/<branch>`, a local tracking branch is created. If it does not exist at
all, `gra` asks whether to create it from origin's default branch; on
confirmation the new branch is pushed to `origin` and set up to track
`origin/<branch>`.

Without a branch, the worktree starts detached at origin's default branch -
instantly usable for looking around, running builds, or letting `gra switch`
pick the real work later:

```sh
gra start
```

If the repository has submodules, they are initialized in the new worktree.

When run inside tmux, `gra start` also opens a tmux window named
`<repo>/<worktree>`, for example `martinus-oans/hare`, starting in the worktree
directory. Use `--no-tmux` to skip that.

Worktree names are unique across all repositories under the gra root: before
choosing, `gra` removes every name that is already taken anywhere and picks a
random one from the rest.

## switch - switch the current worktree to another branch

Run `gra switch BRANCH` inside a worktree to reuse it for other work:

```sh
gra switch feature/search
gra switch bugfix/crash
```

Branch resolution works like `gra start`: existing local branches are switched
to, `origin/<branch>` gets a local tracking branch, and missing branches can be
created from origin's default branch and pushed.

`gra switch` refuses when the worktree has uncommitted changes - commit or
stash first. Git allows a branch to be checked out in only one worktree at a
time, so switching to a branch that is already checked out elsewhere fails with
Git's normal message.

## done - remove the current worktree

Run `gra done` inside a worktree when the work in it is finished:

```sh
gra done
```

`gra done` refuses when the worktree is dirty or when its commits are not in
origin's default branch (squash and cherry-pick merges are recognized via patch
equivalence). `--force` overrides both checks. On removal:

* the worktree directory is removed,
* the local branch is deleted, but only when its changes were verified to be
  merged - with `--force` on an unmerged branch, the branch is kept,
* any tmux window named after the worktree is killed.

With the bash shell integration, `gra done` also moves your shell out of the
removed directory into the repository folder.

## ls - list repositories and worktrees

Run `gra ls` from anywhere to see all repositories under the configured gra
root and every worktree Git knows about:

```sh
gra ls
```

Example output:

```text
Root: /home/me/gra
Repositories: 2  Worktrees: 2

REPOSITORY     WORKTREE  BRANCH          STATUS   REMOTE
martinus-gra   wolf      main            ✓ clean  git@github.com:martinus/gra
martinus-oans  hare      feature/search  ● dirty  git@github.com:martinus/oans
```

Because worktree names carry no meaning, the `BRANCH` column is the primary
information; the name is just an address.

## clean - report or remove clean merged worktrees

Run `gra clean` from anywhere to classify every worktree under the configured
gra root. It prints one table like `gra ls`, with `VERDICT` and `REASON`
columns added:

```sh
gra clean
```

Example output:

```text
Root: /home/me/gra
Repositories: 2  Worktrees: 2

REPOSITORY     WORKTREE  BRANCH   STATUS   VERDICT  REASON
martinus-gra   wolf      feature  ● dirty  keep     uncommitted changes
martinus-oans  hare      old-fix  ✓ clean  remove   merged into origin/main

Dry run. Re-run with --yes to remove 1 worktree(s).
```

Verdicts mean:

* `keep` - the worktree has uncommitted changes or commits that are not merged
  into origin's default branch. A clean worktree that would otherwise be
  removable is also kept when it contains a `.grakeep` file.
* `remove` - the worktree is clean and its `HEAD` is already merged into
  origin's default branch, or its commits are patch-equivalent to changes
  already there after a squash or cherry-pick merge.
* `prune` - Git still knows about the worktree, but the directory no longer
  exists on disk.

By default, `gra clean` is a dry run. Use `--yes` to remove worktrees marked
`remove` and prune missing entries:

```sh
gra clean --yes
```

Before classifying, `gra clean` runs `git fetch --prune origin` in each
repository. Use `--no-fetch` to skip that step.

`gra clean --yes` deletes the local branch of each removed worktree - the
merged or patch-equivalent verification already happened as part of the
verdict. It also kills tmux windows named after removed worktrees. It never
removes dirty worktrees.

## cd - jump to a worktree

Run `gra cd` to choose any worktree under the gra root with `fzf`, or pass a
worktree name to jump directly:

```sh
gra cd        # pick with fzf
gra cd wolf   # jump straight to the worktree named wolf
```

The command prints the selected path. To make `gra cd` change the current Bash
shell's directory, add this to `~/.bashrc` after `gra` is on your `PATH`:

```sh
eval "$(gra shell bash)"
```

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

## tmux - open a worktree in tmux

Run `gra tmux` to choose a worktree with the same `fzf` picker as `gra cd`, or
pass a worktree name directly, then open it in a tmux window. The default
session is `main`; it is created when it does not exist:

```sh
gra tmux        # pick with fzf
gra tmux wolf   # open the worktree named wolf
```

The window starts in the worktree root and is named `<repo>/<worktree>`, for
example `martinus-oans/wolf`, so the window list shows at a glance which
repository each workspace belongs to. If a window with the same name already
exists, `gra tmux` selects it instead of creating a duplicate.

Use `--session` for a different tmux session:

```sh
gra tmux --session work
```

# Working with Claude

The layout is designed so that a coding agent can manage branches itself inside
one worktree. A useful convention for a repository's `CLAUDE.md`:

* to work on another branch in this worktree: commit or stash, then
  `gra switch <branch>`,
* `gra switch` also creates missing branches (from origin's default branch,
  pushed and tracking) after asking for confirmation.

For parallel agents, give each its own worktree with `gra start` - one branch
can only be checked out in one worktree at a time.

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
