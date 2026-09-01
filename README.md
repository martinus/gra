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
gra work warmhare                            # back to that worktree's tmux window
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
> `gra` spot that a clone is a fork, and `tmux` - when you work inside it -
> gets a window per worktree.

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
| [`gra work [target]`](#gra-work) | Create a worktree for a branch - or open a worktree's tmux window |
| [`gra switch [branch]`](#gra-switch) | Move the worktree you are standing in to another branch |
| [`gra done [name]`](#gra-done) | Remove a worktree once its work is in origin |
| [`gra cd [name]`](#gra-cd) | Jump to a worktree, by name or with `fzf` |
| [`gra ls [--fetch]`](#gra-ls) | One table of every repository and worktree |
| [`gra fetch`](#gra-fetch) | `git fetch --prune --all` in every repository, in parallel |
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
local branch tracking `origin/<branch>`, and gets a [tmux
window](#tmux-windows) just like `gra work` gives one.

| Flag | Effect |
| ---- | ------ |
| `--name <name>` | Use a different local directory name |
| `--no-work` | Bare checkout only, no worktree |
| `--no-tmux` | Create the worktree, open no window |
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

The argument is either a worktree name or a branch:

```sh
gra work warmhare         # go to that worktree's tmux window, from anywhere
gra work feature/search   # a new worktree with that branch checked out
gra work OA-2345          # part of a branch name is enough
gra work                  # pick a branch with fzf
```

A **worktree name** is looked up first, because a name identifies one worktree
on the whole machine, and it opens that worktree's [tmux
window](#tmux-windows) - or switches to it when it is already open. Nothing is
created. Anything else is a **branch**.

Without an argument, what it does depends on where you run it:

* **in the repository folder** (next to `.bare`): create a new worktree,
* **inside a worktree**: open that worktree's window, creating nothing,
* **anywhere else**: fail, and say exactly this.

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
`gra.submodules = false`. Then, inside tmux, the worktree gets a [window
named](#tmux-windows) `<repo>/<worktree>` - for example `oans/warmhare`.

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
<summary><b>Opening a worktree again</b></summary>

<br>

A worktree outlives the window it was opened in: close the window, or come
back the next day to a machine that has been rebooted, and the worktree is
still there with nothing around it. Name it from anywhere to get the window
back:

```sh
gra work snowwolf
```

A bare `gra work` inside the worktree does the same. Either way nothing is
created, and an open window is switched to rather than duplicated.

Outside tmux there is no session a window would belong to, so this is the one
case where `gra` says it had nothing to do rather than staying quiet:

```text
not inside tmux; nothing to set up for 'snowwolf'
```

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

Afterwards the worktree's [tmux window](#tmux-windows) is opened or switched
to. The window is named after the worktree, not the branch, so a switch keeps
the window it already has.

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
gra done --force    # dirty or unmerged, remove it without asking
```

On removal the worktree's [tmux window](#tmux-windows) is closed, the
directory is removed, and the local branch is deleted - but only when its
changes were verified to be merged. With `--force` on an unmerged branch, the
branch is kept.

With the bash shell integration, `gra done` also moves your shell out of the
removed directory into the repository folder.

Before removing anything it fetches, works out where the branch stands, and
asks when something is not in order:

```text
'/home/me/gra/oans/snowwolf':
  ✔ commits pushed to branch origin/snow-tier2
  ✔ no local modifications
  ✘ not yet merged to origin/main
  ✘ pull request #4711 open, changes requested

  branch 'snow-tier2' will be kept

continue? [y/N]
```

The dim lines under the checks are what removal costs: modifications that
will be lost, commits a detached HEAD leaves to the reflog, and whether the
branch is deleted or kept.

The fetch is the point of the whole thing: every check reads a
remote-tracking ref, so without it a branch that was squash-merged an hour
ago still looks unmerged. Squash and cherry-pick merges are recognized via
patch equivalence, and a branch the remote deleted after merging counts as
finished, so the usual PR workflow ends in ticks and no question at all.

The pull request line needs [gh](https://cli.github.com/) and a GitHub
remote; without either - or without a network - it simply does not appear.
A half-finished rebase, merge, cherry-pick or bisect gets a line of its own,
since that is the one state removal cannot give back.

Anything but `y` keeps the worktree, so a plain Enter is always the safe
answer. `--force` answers yes without asking and skips the fetch - useful in
scripts, where an unanswered question counts as no.

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

# tmux windows

Inside tmux, a worktree gets one window, named `<repo>/<worktree>`:

| Command | What happens to the window |
| ------- | -------------------------- |
| `gra clone`, `gra work <branch>` | opened for the new worktree |
| `gra work <worktree>`, bare `gra work` inside one | opened, or switched to when already open |
| `gra switch` | opened or switched to, keeping its name |
| `gra done` | closed |

The name is the whole mechanism. There is no config file, nothing to install,
and no state kept anywhere: `gra` asks tmux for the window of that name and
acts on the answer. Two consequences follow.

**A window is never duplicated.** A worktree outlives its window, and every
command that leaves you in a worktree looks the name up before opening
anything - so `gra switch`, a second `gra work`, and reopening a window you
closed yesterday all land in the same place.

**The window need not be in this session.** `gra` looks at every session, so
`gra done snowwolf` closes the window even when it lives in a session you are
not attached to, and even when you run it from a plain terminal.

Outside tmux nothing is opened - there is no session the window would belong
to - and `gra` says so only when opening the window was the whole command:

```text
not inside tmux; nothing to set up for 'snowwolf'
```

tmux does not have to be installed. Every tmux call is best-effort: if it is
missing, or a window went away between the lookup and the command, `gra`
carries on and the git work still happens.

<details>
<summary><b>Closing the window <code>gra</code> is running in</b></summary>

<br>

`gra done` is normally run from the very window it has to close, and closing
that window would kill `gra` before it removes anything. So that one window is
handed to the tmux server, which outlives it:

```sh
tmux run-shell -b "while kill -0 $PID 2>/dev/null; do sleep 0.2; done; \
    [ -d '$WORKTREE' ] || tmux kill-window -t $WINDOW"
```

The wait is what keeps `gra` alive to finish the removal, and the `-d` test is
what makes it safe: a removal that failed leaves the worktree there, and then
the window stays open too. Every other window is closed immediately.

</details>

<details>
<summary><b>Coming from the <code>work.sh</code> / <code>done.sh</code> hooks</b></summary>

<br>

Up to `gra` 5.3 the tmux windows came from two shell hooks, `work.sh` and
`done.sh`, written into each repository next to `.bare`, and `gra hooks` wrote
the missing ones. `gra` no longer reads either file and the `gra hooks`
command is gone; the behaviour they had by default is now `gra`'s own, so
nothing has to be written per repository and repositories cloned by an older
`gra` behave like the rest.

The files are left where they are - `gra` will not touch or delete them. If
you never edited yours, they are dead weight:

```sh
rm ~/gra/*/work.sh ~/gra/*/done.sh
```

If you did edit yours, there is no hook to port them into. Two shapes replace
what they were used for:

* **pane layout** - a `claude` pane, an editor, a monitor - belongs in a shell
  function you call yourself, or in a tmux
  [session/window config](https://github.com/tmux-plugins/tmux-resurrect).
* **preparing the worktree** - symlinking a `compile_commands.json`, copying a
  `.env` - has no hook to run in any more. Put it in a target the build
  already depends on, or run it in the worktree once you are there.

</details>

# Tab completion

The `eval` line installs Bash completion too, so there is nothing else to set
up:

```text
gra <TAB>              install clone fetch ls work switch done cd shell
gra cd <TAB>           warmhare goldfish snowwolf    worktree names
gra done <TAB>         warmhare goldfish snowwolf --force
gra work <TAB>         worktree names, plus branches inside a repository
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
