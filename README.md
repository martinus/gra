<div align="center">

# gra - Git Repo Admin

**One flat root. Bare checkouts. Disposable worktrees.**

A tiny worktree-first clone helper in a single Python file - no daemon, no
config, no lock-in.

[![tests](https://github.com/martinus/gra/actions/workflows/tests.yml/badge.svg)](https://github.com/martinus/gra/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![install](https://img.shields.io/badge/install-one%20file-brightgreen)](gra)
[![license](https://img.shields.io/github/license/martinus/gra)](LICENSE)

</div>

---

## A minute with gra

```sh
gra clone git@github.com:martinus/oans.git   # into ~/gra/oans, with a worktree ready
gra cd warmhare                              # jump into that worktree, from anywhere
gra work OA-2345                             # another worktree, on that branch
gra switch main                              # or reuse the one you are standing in
gra done                                     # throw it away once the work is merged
gra ls                                       # what do I have, and where is it?
```

Every repository lives once, as a bare checkout, and all work happens in
short-named worktrees next to it:

```text
~/gra
├── oans
│   ├── .bare        <- the repository itself
│   ├── warmhare     <- a worktree, on main
│   └── goldfish     <- another one, on feature/search
└── nanobench
    ├── .bare
    └── snowwolf
```

* **No default checkout.** No branch is ever pinned by a checkout you do not
  use, so any worktree can be on `main`, rebase onto it, or switch away.
* **Names, not paths.** Worktree names are word pairs - `warmhare`,
  `goldfish`, `snowwolf` - always eight letters and unique across **all**
  repositories, so one name identifies one worktree on the whole machine.
* **The same names everywhere.** They are derived from the repository rather
  than drawn at random, so cloning `oans` on your laptop and on your desktop
  gives you the same name in both places.
* **Worktrees are cheap.** A worktree is just a workspace, unrelated to the
  branch it has checked out: make one, switch it around, throw it away.

## Install

```sh
python3 -c "$(curl -fsLS https://raw.githubusercontent.com/martinus/gra/refs/heads/main/gra)" install
```

That is the whole installation, and re-running it is how you upgrade. Restart
your shell afterwards.

> [!NOTE]
> Needs **Git** and **Python 3.10+**. [`fzf`](https://github.com/junegunn/fzf)
> powers the worktree and branch pickers, [`gh`](https://cli.github.com/) lets
> `gra` spot that a clone is a fork. `gra` itself never calls `tmux` - the
> hooks it writes for you do.

<details>
<summary><b>What it writes, and where</b></summary>

<br>

The script goes to `~/.local/bin/gra`, and this block is appended to
`~/.bashrc`:

```sh
# gra
export PATH="$HOME/.local/bin:$PATH"
eval "$(gra shell bash)"
```

The `PATH` line is added only when `~/.local/bin` is not on your `PATH`
already, and the block is added only once - re-running touches nothing else.
When there is no `~/.bashrc` (`gra shell` only speaks bash) nothing is written
and the lines to add are printed instead.

That one `eval` is what makes `gra cd` change directories, `gra done` leave
the removed directory, and `<TAB>` complete worktrees, repositories and
branches.

</details>

<details>
<summary><b>Choosing where repositories live</b></summary>

<br>

The default root is `~/gra`. Configure a different one in `~/.gitconfig`:

```sh
git config --global gra.root ~/develop
```

</details>

## Commands

| Command | What it does |
| ------- | ------------ |
| [`gra clone <url>`](#gra-clone) | Clone into `~/gra/<repo>` as a bare checkout, with a worktree ready to use |
| [`gra work [branch]`](#gra-work) | Create a worktree for a branch - or set the one you are in up again |
| [`gra switch [branch]`](#gra-switch) | Move the worktree you are standing in to another branch |
| [`gra done [name]`](#gra-done) | Remove a worktree once its work is in origin |
| [`gra cd [name]`](#gra-cd) | Jump to a worktree, by name or with `fzf` |
| [`gra ls [--fetch]`](#gra-ls) | One table of every repository and worktree |
| [`gra fetch`](#gra-fetch) | `git fetch --prune --all` in every repository, in parallel |
| [`gra hooks`](#gra-hooks) | Write missing `work.sh` / `done.sh` hooks |
| [`gra install`](#gra-install) | Install or upgrade `gra` itself |

Everything runs from anywhere. The exceptions are the commands that act on
*where you are standing*: `gra switch`, and a bare `gra work` or `gra done`.

---

# Reference

## `gra clone`

Clones one repository as a bare checkout into `~/gra/<repo>/.bare` and opens a
worktree next to it:

```sh
gra clone git@github.com:martinus/oans.git
```

```text
~/gra/oans
├── .bare
└── warmhare    <- checked out main
```

The worktree is ready to work in: it checks out origin's default branch as a
local branch tracking `origin/<branch>`, and runs the repository's `work.sh`
hook just like `gra work` does.

| Flag | Effect |
| ---- | ------ |
| `--name <name>` | Use a different local directory name |
| `--no-work` | Bare checkout only, no worktree |
| `--no-hook` | Create the worktree, skip the hook |
| `--no-submodules` | Never initialize submodules in this repository |
| `--no-upstream` | Skip the fork lookup |

> [!TIP]
> The local name is the repository name (`oans` above). If it is taken, `gra`
> stops and suggests a distinct one - for two owners of the same repository,
> disambiguating by owner works well:
> ```sh
> gra clone git@github.com:andreas/oans.git --name oans-andreas
> ```

<details>
<summary><b>Forks get an <code>upstream</code> remote</b></summary>

<br>

Cloning a GitHub fork also adds an `upstream` remote pointing at the
repository it was forked from:

```text
added remote 'upstream' -> git@github.com:upstream/oans.git
run 'gra fetch' for its branches
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

</details>

<details>
<summary><b>Submodules are a decision about the repository</b></summary>

<br>

Pass `--no-submodules` for a repository whose submodules you never want. It
records `gra.submodules = false` in the bare checkout, so every later
`gra work` in that repository skips them too - the flag is a decision about
the repository, not about one clone. It is ordinary Git config, so you can
change your mind:

```sh
git -C ~/gra/oans/.bare config gra.submodules true    # this repository
git config --global gra.submodules false              # everywhere
```

</details>

<details>
<summary><b>How the bare checkout is set up</b></summary>

<br>

It is made to behave like a normal clone:

* the fetch refspec tracks all of origin's branches as `origin/<branch>`
  remote-tracking refs, and never mirrors them into local branches,
* `origin/HEAD` points at origin's default branch,
* reflogs are enabled (bare repositories disable them by default),
* `.claude/worktrees/` is added to the shared local Git exclude file so
  tool-managed paths do not show up as untracked files in any worktree.

A remote without commits has no default branch to check out; `gra` says so and
keeps the clone.

</details>

## `gra work`

What it does depends on where you run it:

* **in the repository folder** (next to `.bare`): create a new worktree,
* **inside a worktree**: run its `work.sh` hook again, creating nothing,
* **anywhere else**: fail, and say exactly this.

```sh
gra work feature/search   # a worktree with that branch checked out
gra work OA-2345          # part of a name is enough
gra work                  # pick a branch with fzf
```

```text
~/gra/oans
├── .bare
└── warmhare    <- checked out feature/search
```

A branch always means a *new* worktree, even from inside another one, so a
second task never needs a `cd ..` first. If the branch only exists as
`origin/<branch>`, a local tracking branch is created. If it does not exist at
all, `gra` asks whether to create it from origin's default branch; on
confirmation the new branch is pushed to `origin` and set up to track
`origin/<branch>`.

Without a branch, `gra work` opens an `fzf` picker over all branches, the ones
with the newest commits first - the branch you are here for is almost always
near the top. Branches already checked out in a worktree are not offered,
because Git allows a branch in only one worktree at a time. The first entry
starts the worktree detached at origin's default branch instead - instantly
usable for looking around, running builds, or letting a later `gra switch`
pick the real work.

If the branch you name is already checked out somewhere, `gra` names that
worktree instead of leaving you with Git's message:

```text
ERROR: 'main' is already checked out in 'calmpuma'; work there with 'gra cd calmpuma'
```

Submodules are initialized in the new worktree unless the repository has
`gra.submodules = false`. Afterwards the repository's [`work.sh`](#hooks) hook
runs inside it - as written by `gra clone`, that opens a tmux window named
`<repo>/<worktree>`, for example `oans/warmhare`.

<details>
<summary><b>Finding a branch you did not name</b></summary>

<br>

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

</details>

<details>
<summary><b>Setting a worktree up again</b></summary>

<br>

A worktree outlives the window it was opened in: close the window, or come
back the next day to a machine that has been rebooted, and the worktree is
still there with nothing around it. Run `gra work` inside it - with the shell
integration, `gra cd snowwolf` and then `gra work` from anywhere - and
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

</details>

<details>
<summary><b>How names are chosen</b></summary>

<br>

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

</details>

## `gra switch`

To reuse the worktree you are standing in for other work instead of creating
a new one:

```sh
gra switch feature/search   # by name, or part of one
gra switch                  # pick with fzf
```

Branch resolution is the same as [`gra work`](#gra-work)'s: existing local
branches are switched to, `origin/<branch>` gets a local tracking branch,
missing branches can be created from origin's default branch and pushed, and
part of a name is enough when it matches one branch. Without a branch, an
`fzf` picker offers all branches, newest commits first - minus those already
checked out in a worktree, which a switch could never reach.

The `work.sh` hook runs afterwards, with `GRA_BRANCH` set to the branch you
switched to - the worktree is set up for the new work the same way a fresh one
would be.

> [!IMPORTANT]
> `gra switch` refuses when the worktree has uncommitted changes - commit or
> stash first. Switching to a branch checked out elsewhere is refused too,
> naming the worktree that holds it. Run anywhere but inside a worktree it
> fails: there is no checkout there whose branch it could change.

## `gra done`

Run it inside a worktree when the work in it is finished, or name one from
anywhere:

```sh
gra done            # the worktree you are in
gra done snowwolf   # from anywhere
gra done --force    # dirty or unmerged, remove it anyway
```

On removal the [`done.sh`](#hooks) hook runs while the worktree is still
there, the directory is removed, and the local branch is deleted - but only
when its changes were verified to be merged. With `--force` on an unmerged
branch, the branch is kept.

With the bash shell integration, `gra done` also moves your shell out of the
removed directory into the repository folder.

> [!WARNING]
> `gra done` refuses when the worktree is dirty, or when its commits are not
> in origin's default branch. Squash and cherry-pick merges are recognized via
> patch equivalence, so the usual PR workflow does not need `--force`.

## `gra cd`

```sh
gra cd            # pick with fzf
gra cd snowwolf   # jump straight to the worktree named snowwolf
```

The command prints the selected path; the shell integration is what turns that
into an actual `cd`. `gra install` adds it for you, or add it yourself:

```sh
eval "$(gra shell bash)"
```

## `gra ls`

One table of every repository under the gra root and every worktree Git knows
about:

```sh
gra ls
gra ls --fetch    # refresh every repository first
```

```text
Root: /home/me/gra
Repositories: 2  Worktrees: 3

   REPOSITORY  WORKTREE  BRANCH          SYNC   STATUS   REMOTE
   gra         snowwolf  main            ↑2     ✓ clean  git@github.com:martinus/gra
▶  oans        warmhare  feature/search  ↓1     ● dirty  git@github.com:martinus/oans
               goldfish  main                   ✓ clean
```

`▶` is the worktree you are standing in. Because worktree names carry no
meaning, `BRANCH` is the primary information - the name is just an address.

`SYNC` is how far the branch is from its upstream: `↑2` is two commits to
push, `↓1` is one to pull, blank is in sync or has no upstream, and `-` means
the question does not apply (detached, or no upstream). It reads local refs
only - `gra ls` never goes to the network - so it is as fresh as your last
fetch. `--fetch` is [`gra fetch`](#gra-fetch) followed by `gra ls`.

## `gra fetch`

Runs `git fetch --prune --all` in every repository under the gra root, several
at a time:

```sh
gra fetch
```

```text
Fetching 12 repositories
fetched 12 repositories
```

Every remote, not just `origin`: a fork's `upstream` is exactly the remote
that goes stale. Only remote-tracking refs move - no worktree, branch, or
uncommitted change is touched - so it is safe to run at any time, and it is
what makes the `SYNC` column of `gra ls` current.

A repository that cannot be reached is named with the reason, and the others
are still fetched:

```text
Fetching 12 repositories
oans: fatal: could not read from remote repository.
fetched 11 of 12 repositories
```

## `gra hooks`

```sh
gra hooks
```

Writes `work.sh` and `done.sh` into every repository under the gra root that
is missing them, and leaves existing ones alone - so it cannot overwrite your
edits and is safe to re-run. Repositories cloned before hooks existed are what
this is for.

## `gra install`

```sh
gra install
```

Writes `gra` to `~/.local/bin/gra` and makes it executable, replacing whatever
is there - including a symlink left by an older installation. See
[Install](#install) for the `~/.bashrc` block it adds.

<details>
<summary><b>Upgrading, and installing a specific version</b></summary>

<br>

`gra install` compares itself against the version on `main` and installs
whichever is newer, so re-running it is how you upgrade:

```text
downloading https://raw.githubusercontent.com/martinus/gra/main/gra
upgrading gra 1.2.0 -> 1.3.0
installed gra 1.3.0 to '/home/me/.local/bin/gra'
```

Ties go to the local script, so `./gra install` from a checkout still installs
that checkout. Run through `python3 -c` there is nothing local, so the
download is what gets installed - that is the one-liner above.

If the lookup fails - no network, GitHub down - `gra` says so and installs the
local script anyway; a failed check never costs you a working install.

Run from a file, `--no-check` installs that file without looking online, which
is what you want offline or when installing an older branch on purpose.
Through `python3 -c` it changes nothing: with no local script the download is
the only thing there is to install.

</details>

---

# Hooks

`gra` runs two scripts from the repository container, next to `.bare`:

| Hook | When | Working directory |
| ---- | ---- | ----------------- |
| `work.sh` | whenever `gra` leaves you in a worktree | that worktree |
| `done.sh` | before `gra done` removes one | the container |

Both receive:

| Variable | Value |
| -------- | ----- |
| `GRA_WORKTREE` | absolute path to the worktree |
| `GRA_REPO` | repository name, e.g. `nanobench` |
| `GRA_WORD` | worktree name, e.g. `warmhare` |
| `GRA_BRANCH` | checked-out branch, or empty when detached |
| `GRA_PID` | the `gra` running the hook, for work that has to outlive it |

`gra clone` writes both, executable and working: out of the box `work.sh`
opens a tmux window for the new worktree and `done.sh` closes it again. They
live in the container rather than the repository, so they are personal and
per-machine and are never committed. `gra` writes them once and never touches
them afterwards - edit them and they stay edited. `chmod -x work.sh` turns one
off; deleting it does the same.

> [!NOTE]
> `gra` owns what a worktree *is* - its branch, its submodules, its name - and
> the hooks own what you *do* with it. That is why submodules are initialized
> by `gra` and tmux windows are not: `gra` has no tmux code at all.

<details>
<summary><b>Writing your own: the one rule</b></summary>

<br>

`work.sh` runs once per worktree only in the simplest case. It also runs after
`gra switch` moves a worktree to another branch, and again whenever `gra work`
is run inside the worktree. So it must be safe to run twice: as written by
`gra clone` it looks for its window before opening one, and selects the window
that is already there instead of opening a second one of the same name.
Anything you add should follow that shape - `ln -sf` rather than `ln -s`, and
no step that would disturb a build running in a pane.

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

The second rule only `done.sh` has to follow: **do not close the window you
are running in.** `gra done` is normally run from the very window that is
about to be closed, and closing it takes `gra` with it - before it removes
anything. So the hook checks whether the window it found is its own, and hands
that one to the tmux server, which outlives it:

```sh
tmux run-shell -b "\
    while kill -0 $GRA_PID 2>/dev/null; do sleep 0.2; done
    [ -d '$GRA_WORKTREE' ] || tmux kill-window -t $id"
```

`GRA_PID` is what makes the wait possible, and the `-d` test is what makes it
safe: a removal that failed leaves the worktree there, and then the window
stays open too. Any other work that has to outlive `gra` can wait the same
way.

</details>

<details>
<summary><b>Upgrading a hook written by an older gra</b></summary>

<br>

`gra` never rewrites a hook you have - `gra hooks` only writes the missing
ones - so a hook from an older `gra` keeps whatever it was written with, and
two of them are worth patching by hand.

A `done.sh` written before `gra` 5.1 closes its window straight away. Run
`gra done` from inside that window and it kills `gra` mid-removal: the window
disappears and the worktree is still there, still registered with Git. Paste
the deferred close from above in, or replace the whole hook with the current
one:

```sh
mv done.sh done.sh.bak && gra hooks    # per repository
```

A `work.sh` written before re-running it was possible has no window lookup,
and until you paste it in, `gra switch` and a re-run `gra work` open a second
window of the same name - which `done.sh` then closes one of. Copy that block
in ahead of `new-window`.

Repositories cloned with `gra` 1.x have no hooks at all and open no windows;
`gra hooks` gives every repository the hooks it is missing, in one go. A
`.tmux-setup` file is no longer read, and renaming it will not help: it
targets a `GRA_WINDOW` that no longer exists, because `gra` no longer opens
the window. Port what is in it into `work.sh`.

</details>

# Tab completion

The `eval` line installs Bash completion too, so there is nothing else to set
up:

```text
gra <TAB>              install clone fetch ls work switch done cd shell hooks
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

# Recipes

<details>
<summary><b>Opening a worktree in tmux</b></summary>

<br>

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

</details>

<details>
<summary><b>Working with Claude</b></summary>

<br>

The layout is designed so that a coding agent can manage branches itself
inside one worktree. A useful convention for a repository's `CLAUDE.md`:

* to work on another branch in this worktree: commit or stash, then
  `gra switch <branch>`,
* `gra switch` also creates missing branches (from origin's default branch,
  pushed and tracking) after asking for confirmation.

For parallel agents, give each its own worktree with `gra work` - one branch
can only be checked out in one worktree at a time.

</details>

# Development

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

To use your working copy, run `./gra install --no-check` from the checkout.
Without the flag a checkout behind `main` installs `main` instead.

# Alternatives

* [ghq](https://github.com/x-motemen/ghq) was the main inspiration for `gra`.
  gra is much simpler, a single python file, git only, and integrates easily
  with VSCode.
* [ghr](https://github.com/siketyan/ghr) is another ghq clone, written in
  Rust, but it currently did not work with non github URLs. I like the bash
  integration.
* [rhq](https://github.com/ubnt-intrepid/rhq) another one in rust.
* [projj](https://github.com/popomore/projj)
