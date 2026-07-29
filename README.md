# gra - Git Repo Admin

`gra` is a tiny worktree-first clone helper. It keeps repositories under a flat
root directory as bare checkouts, and all work happens in short-named worktrees
next to them:

```text
~/gra
└── oans
  ├── .bare
  ├── warmhare
  └── goldfish
```

There is no default checkout: no branch is ever pinned by a checkout you do not
use, so any worktree can be on `main`, rebase onto it, or switch to any branch
freely.

Worktree names are word pairs (`warmhare`, `goldfish`, `snowwolf`, ...), always
eight letters, unique across **all** repositories, and unrelated to the branch
they have checked out. They are derived from the repository rather than drawn
at random, so cloning `oans` on your laptop and on your desktop gives you the
same name in both places. A worktree is just a workspace: create one with
`gra work`, switch branches inside it with `gra switch`, and throw it away with
`gra done`.
Because names are globally unique, a name like `snowwolf` identifies one
worktree across the whole machine - in `gra cd snowwolf`, in the tmux window
names the default hook gives them, and in conversation.

The default root is `~/gra`. Configure a different root in `~/.gitconfig`:

```sh
git config --global gra.root ~/develop
```

# Installation

`gra` needs Git and Python 3.10 or newer, `fzf` for the worktree and branch
pickers, and `gh` to spot that a clone is a fork.
`gra` itself never calls `tmux`; the hooks it writes for you do, so `tmux` is
only needed if you keep them.

```sh
python3 -c "$(curl -fsLS https://raw.githubusercontent.com/martinus/gra/refs/heads/main/gra)" install
```

That is the whole installation. It writes the script to `~/.local/bin/gra` and
appends this block to `~/.bashrc`, so that `gra` is on your `PATH` and the shell
integration makes `gra cd` change directories, `gra done` leave the removed
directory, and `<TAB>` complete worktrees, repositories and branches:

```sh
# gra
export PATH="$HOME/.local/bin:$PATH"
eval "$(gra shell bash)"
```

Restart your shell afterwards.

# Commands

## install - install or upgrade gra

```sh
gra install
```

Writes `gra` to `~/.local/bin/gra` and makes it executable, replacing whatever
is there - including a symlink left by an older installation. The `PATH` line
is added only when `~/.local/bin` is not on your `PATH` already, and the
`~/.bashrc` block is added only once, so re-running the command touches nothing
else.

When there is no `~/.bashrc` - `gra shell` only speaks bash - nothing is
written and the lines to add are printed instead.

### Upgrading

`gra install` compares itself against the version on `main` and installs
whichever is newer, so re-running it is how you upgrade:

```text
downloading https://raw.githubusercontent.com/martinus/gra/main/gra
upgrading gra 1.2.0 -> 1.3.0
installed gra 1.3.0 to '/home/me/.local/bin/gra'
```

Ties go to the local script, so `./gra install` from a checkout still installs
that checkout. Run through `python3 -c` there is nothing local, so the download
is what gets installed - that is the one-liner above.

If the lookup fails - no network, GitHub down - `gra` says so and installs the
local script anyway; a failed check never costs you a working install.

Run from a file, `--no-check` installs that file without looking online, which
is what you want offline or when installing an older branch on purpose.
Through `python3 -c` it changes nothing: with no local script the download is
the only thing there is to install.

## clone - clone a remote repository

Clones one repository as a bare checkout into `~/gra/<repo>/.bare` and opens a
worktree next to it:

```sh
gra clone git@github.com:martinus/oans.git
```

This creates:

```text
~/gra/oans
├── .bare
└── warmhare    <- checked out main
```

The worktree is ready to work in: it checks out origin's default branch as a
local branch tracking `origin/<branch>`, and runs the repository's `work.sh`
hook just like `gra work` does. Use `--no-work` for the bare checkout alone, or
`--no-hook` to skip the hook. A remote without commits has no default branch to
check out; `gra` says so and keeps the clone.

Cloning a GitHub fork also adds an `upstream` remote pointing at the
repository it was forked from:

```text
added remote 'upstream' -> git@github.com:upstream/oans.git
run 'git fetch upstream' to get its branches
```

A fork is a GitHub concept rather than a Git one, so `gra` asks `gh`, which
carries its own login - private forks work and `gra` never handles a token.
Without `gh` installed it says so and carries on; for a remote that is not on
`github.com` it says nothing, because there is nothing it could ask. The
remote is added but not fetched, so cloning stays as quick as it was.

`--no-upstream` skips the lookup once, and `git config --global gra.upstream
false` skips it for good. Only `gra clone` does this, so a repository you
cloned earlier keeps whatever remotes it has; `git remote add upstream <url>`
is the one-off.

Pass `--no-submodules` for a repository whose submodules you never want. It
records `gra.submodules = false` in the bare checkout, so every later
`gra work` in that repository skips them too - the flag is a decision about
the repository, not about one clone. It is ordinary Git config, so you can
change your mind:

```sh
git -C ~/gra/oans/.bare config gra.submodules true    # this repository
git config --global gra.submodules false              # everywhere
```

The local name is the repository name (`oans` above). If that name is already
taken, `gra` stops and suggests a distinct one; use `--name` to choose it - for
two owners of the same repository, disambiguating by owner works well:

```sh
gra clone git@github.com:andreas/oans.git --name oans-andreas
```

The bare checkout is set up to behave like a normal clone:

* the fetch refspec tracks all of origin's branches as `origin/<branch>`
  remote-tracking refs, and never mirrors them into local branches,
* `origin/HEAD` points at origin's default branch,
* reflogs are enabled (bare repositories disable them by default),
* `.claude/worktrees/` and `.grakeep` are added to the shared local Git
  exclude file so tool-managed paths and keep markers do not show up as
  untracked files in any worktree.

## work - create a new worktree, or set one up again

What `gra work` does depends on where you run it:

* **in the repository folder** (next to `.bare`): create a new worktree,
* **inside a worktree**: run its `work.sh` hook again, creating nothing,
* **anywhere else**: fail, and say exactly this.

Creating a worktree picks an unused name for the repository and checks the
branch out next to `.bare`:

```sh
gra work feature/search
```

```text
~/gra/oans
├── .bare
└── warmhare    <- checked out feature/search
```

With a branch, `gra work` checks it out - and a branch always means a new
worktree, even from inside another one, so a second task never needs a
`cd ..` first. If the branch only exists as `origin/<branch>`, a local
tracking branch is created. If it does not exist at all, `gra` asks whether to
create it from origin's default branch; on confirmation the new branch is
pushed to `origin` and set up to track `origin/<branch>`.

Without a branch, in the repository folder, `gra work` opens an `fzf` picker
over all branches, the ones with the newest commits first - the branch you
are here for is almost always near the top. Branches already checked out in a
worktree are not offered, because Git allows a branch in only one worktree at
a time. The first entry starts the worktree detached at origin's default
branch instead - instantly usable for looking around, running builds, or
letting a later `gra switch` pick the real work.

If the branch you name is already checked out somewhere, `gra` names that
worktree instead of leaving you with Git's message:

```text
ERROR: 'main' is already checked out in 'calmpuma'; work there with 'gra cd calmpuma'
```

If the repository has submodules, they are initialized in the new worktree,
unless the repository has `gra.submodules = false` - see
[clone](#clone---clone-a-remote-repository).

`gra work` then runs the repository's `work.sh` hook inside the new worktree.
As written by `gra clone` that opens a tmux window named `<repo>/<worktree>`,
for example `oans/warmhare`.

### Setting a worktree up again

A worktree outlives the window it was opened in: close the window, or come
back the next day to a machine that has been rebooted, and the worktree is
still there with nothing around it. Run `gra work` inside it - with the
shell integration, `gra cd rail` and then `gra work` from anywhere - and
`work.sh` runs again for it, creating nothing.

`GRA_BRANCH` is read from the worktree, so a detached one gets the empty value
creating it would have given the hook.

Where creating a worktree shrugs at a missing `work.sh` - it made a worktree
either way - the re-run refuses, because there would be nothing left to show
for it:

```text
ERROR: '/home/you/gra/oans' has no 'work.sh'; 'gra hooks' writes missing hooks
```

A `work.sh` you turned off with `chmod -x` is a decision rather than a
mistake, so that is a note and not an error.

### Finding a branch you did not name

BRANCH can be part of a branch name rather than all of it, so a ticket key
finds the branch someone named after it:

```sh
gra work OA-2345      # checks out mla/OA-2345-per-processor-properties
```

An exact branch always wins, so `gra work feature` takes `feature` even when
`feature-extended` exists. Matching is case-insensitive and covers branches on
`origin` you have fetched but never checked out. Several matches are listed
rather than guessed between:

```text
ERROR: 'OA-7777' matches several branches; name one:
  mla/OA-7777-first
  mla/OA-7777-second
```

Nothing matching means the old behaviour: `gra` offers to create the branch
from origin's default branch. The same resolution applies to `gra switch`.

### How names are chosen

A name is a descriptor and a noun run together, each from its own list of
four-letter words - `warmhare`, `goldfish`, `snowwolf`. A hash of the
repository's remote - `owner/repo`, so an SSH clone and an HTTPS clone agree -
shuffles both lists into an order private to that repository, and the shuffled
lists are paired so that every combination appears exactly once, with
consecutive names sharing neither word. `gra work` takes the first name in
that order which no worktree anywhere under the gra root is using.

Every choice starts at the front of the list, so a repository's second worktree
gets its second name simply because the first one is occupied. A name held by
another repository is skipped the same way, and `gra done` frees a name for the
next `gra work` to reclaim. Machines only disagree when one of them let another
repository claim a contested name first, and then only that repository shifts.

### Hooks

`gra` runs two scripts from the repository container, next to `.bare`:

| Hook      | When                                          | Working directory |
| --------- | --------------------------------------------- | ----------------- |
| `work.sh` | whenever `gra` leaves you in a worktree        | that worktree     |
| `done.sh` | before `gra done` or `gra clean` removes one  | the container     |

`work.sh` runs once per worktree only in the simplest case. It also runs after
`gra switch` moves a worktree to another branch, and again whenever `gra work`
is run inside the worktree. So it must be safe to run twice: as written by `gra clone`
it looks for its window before opening one, and selects the window that is
already there instead of opening a second one of the same name. Anything you
add should follow that shape - `ln -sf` rather than `ln -s`, and no step that
would disturb a build running in a pane.

`gra` knows nothing about what is in them. It has no tmux code at all: opening
a window, laying out panes and closing it again are things the hooks do,
which is why they are shell scripts and not options.

The line is that `gra` owns what a worktree *is* - its branch, its submodules,
its name - and the hooks own what you *do* with it. That is why submodules are
initialized by `gra` and windows are not.

Both receive:

| Variable       | Value                                       |
| -------------- | ------------------------------------------- |
| `GRA_WORKTREE` | absolute path to the worktree               |
| `GRA_REPO`     | repository name, e.g. `nanobench`           |
| `GRA_WORD`     | worktree name, e.g. `warmhare`              |
| `GRA_BRANCH`   | checked-out branch, or empty when detached  |

`gra clone` writes both, executable and working: out of the box `work.sh`
opens a tmux window for the new worktree and `done.sh` closes it again. They
live in the container rather than the repository, so they are personal and
per-machine and are never committed. `gra` writes them once and never touches
them afterwards - edit them and they stay edited. `chmod -x work.sh` turns one
off; deleting it does the same.

Read them - they are short, commented, and they are the documentation for what
happens around a worktree. `work.sh` goes to the window or opens it:

```sh
window_name="$GRA_REPO/$GRA_WORD"

open=$(tmux list-windows -a -F '#{window_id} #{window_name}' \
    | awk -v name="$window_name" '$2 == name { print $1; exit }')
if [ -n "$open" ]; then
    tmux select-window -t "$open"
    exit 0
fi

window=$(tmux new-window -P -F '#{window_id}' \
    -n "$window_name" -c "$GRA_WORKTREE")
```

and `done.sh` closes the window of that name again. The name is the only thing
the two have to agree on, so change it in both. The rest of `work.sh` is a
commented-out pane layout - a `claude` pane, an editor, a monitor - to
uncomment or replace.

A `work.sh` written before re-running it was possible has no such lookup, and
`gra` will not add one: it never rewrites a hook you have, and `gra hooks`
only writes the missing ones. Until you paste the lookup in, `gra switch` and
a re-run `gra work` open a second window of the same name - which `done.sh`
then closes one of. Copy the block above in ahead of `new-window`.

### Upgrading from 1.x

Only `gra clone` writes hooks, so repositories you cloned with an older `gra`
have none and open no windows. `gra hooks` gives every repository the hooks it
is missing, in one go. A `.tmux-setup` file is no longer read, and renaming it
will not help: it targets a `GRA_WINDOW` that no longer exists, because gra no
longer opens the window. Port what is in it into `work.sh`.

## switch - switch the current worktree to another branch

To reuse the worktree you are standing in for other work instead of creating
a new one:

```sh
gra switch feature/search   # by name, or part of one
gra switch                  # pick with fzf
```

Branch resolution is the same as `gra work`'s: existing local branches are
switched to, `origin/<branch>` gets a local tracking branch, missing branches
can be created from origin's default branch and pushed, and part of a name is
enough when it matches one branch. Without a branch, an `fzf` picker offers
all branches, the ones with the newest commits first - minus those already
checked out in a worktree, which a switch could never reach.

`gra switch` refuses when the worktree has uncommitted changes - commit or
stash first. Git allows a branch in only one worktree at a time, so switching
to one checked out elsewhere is refused too, naming the worktree that holds
it. Run anywhere but inside a worktree it fails: there is no checkout there
whose branch it could change.

The `work.sh` hook runs afterwards, with `GRA_BRANCH` set to the branch you
switched to - the worktree is set up for the new work the same way a fresh
one would be.

## done - remove a worktree

Run `gra done` inside a worktree when the work in it is finished, or name one
from anywhere:

```sh
gra done            # the worktree you are in
gra done snowwolf   # from anywhere
```

`gra done` refuses when the worktree is dirty or when its commits are not in
origin's default branch (squash and cherry-pick merges are recognized via patch
equivalence). `--force` overrides both checks. On removal:

* the `done.sh` hook runs, while the worktree is still there,
* the worktree directory is removed,
* the local branch is deleted, but only when its changes were verified to be
  merged - with `--force` on an unmerged branch, the branch is kept.

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

REPOSITORY  WORKTREE  BRANCH          SYNC   STATUS   REMOTE
gra         snowwolf  main            ↑2     ✓ clean  git@github.com:martinus/gra
oans        warmhare  feature/search  ↓1     ● dirty  git@github.com:martinus/oans
```

Because worktree names carry no meaning, the `BRANCH` column is the primary
information; the name is just an address.

`SYNC` is how far the branch is from its upstream: `↑2` is two commits to
push, `↓1` is one to pull, and blank is in sync or has no upstream. It reads
local refs only - `gra ls` never goes to the network - so it is as fresh as
your last fetch. A `-` means the question does not apply: a detached worktree,
or a branch with no upstream. To refresh it, fetch (`gra clean` does, for every
repository) and run `gra ls` again.

## hooks - write missing hooks

```sh
gra hooks
```

Writes `work.sh` and `done.sh` into every repository under the gra root that
is missing them, and leaves existing ones alone - so it cannot overwrite your
edits and is safe to re-run.

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

REPOSITORY  WORKTREE  BRANCH   STATUS   VERDICT  REASON
gra         snowwolf  feature  ● dirty  keep     uncommitted changes
oans        warmhare  old-fix  ✓ clean  remove   merged into origin/main

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
verdict. It runs each repository's `done.sh` before removing a worktree, like
`gra done` does. It never removes dirty worktrees.

## cd - jump to a worktree

Run `gra cd` to choose any worktree under the gra root with `fzf`, or pass a
worktree name to jump directly:

```sh
gra cd            # pick with fzf
gra cd snowwolf   # jump straight to the worktree named snowwolf
```

The command prints the selected path. To make `gra cd` change the current Bash
shell's directory, add this to `~/.bashrc` after `gra` is on your `PATH`:

```sh
eval "$(gra shell bash)"
```

`gra install` adds that line for you.

## Tab completion

The same line installs Bash completion, so there is nothing else to set up:

```text
gra <TAB>              install clone ls work switch done cd shell hooks clean
gra cd <TAB>           warmhare goldfish snowwolf    worktree names
gra done <TAB>         warmhare goldfish snowwolf --force
gra work <TAB>         branches, inside a repository
gra switch <TAB>       branches, inside a repository
gra done -<TAB>        --force
```

What it offers follows the same rule the commands do, so the completion and
the command never disagree about what an argument means. Flags are offered
once you type a `-`, so a single worktree name still completes on its own.

Completion never runs `gra` - it reads the gra root and asks `git` for
branches, which keeps `<TAB>` instant instead of paying for a Python start
every time.

## Opening a worktree in tmux

There is no `gra tmux` command - `gra` has no tmux code. `gra cd` prints a
path, so a shell function covers it:

```sh
gratmux() {
    local path name
    path="$(gra cd "$@")" || return
    name="$(basename "$(dirname "$path")")/$(basename "$path")"
    tmux select-window -t "$name" 2>/dev/null ||
        tmux new-window -n "$name" -c "$path"
}
```

# Working with Claude

The layout is designed so that a coding agent can manage branches itself inside
one worktree. A useful convention for a repository's `CLAUDE.md`:

* to work on another branch in this worktree: commit or stash, then
  `gra switch <branch>`,
* `gra switch` also creates missing branches (from origin's default
  branch, pushed and tracking) after asking for confirmation.

For parallel agents, give each its own worktree with `gra work` - one branch
can only be checked out in one worktree at a time.

# Development

Install test dependencies and run the suite with:

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

To use your working copy, run `./gra install --no-check` from the checkout.
Without the flag a checkout behind `main` installs `main` instead.

# Alternatives

* [ghq](https://github.com/x-motemen/ghq) was the main inspiration for `gra`. gra is much simpler,
  a single python file, git only, and integrates easily with VSCode.
* [ghr](https://github.com/siketyan/ghr) is another ghq clone, written in Rust, but it currently
  did not work with non github URLs. I like the bash integration.
* [rhq](https://github.com/ubnt-intrepid/rhq) Another one in rust
* [projj](https://github.com/popomore/projj)
