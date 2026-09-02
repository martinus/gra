---
name: gra
description: Branch and worktree workflow in a repository managed by gra - a flat root of bare checkouts with named worktrees beside them (~/gra/<repo>/.bare and ~/gra/<repo>/warmhare). Use when work needs another branch or a second workspace, when moving between worktrees, or when a finished worktree should be removed.
---

The repository is `<root>/<repo>/.bare`, and every worktree is
`<root>/<repo>/<name>`. A name such as `warmhare` identifies one worktree on
the whole machine, so it needs no path and no repository to go with it.

- **Work on another branch**: `gra work <branch>` makes a worktree for it and
  opens it. In a script or a hook use `gra work --path <branch>`, which prints
  only the new worktree's path. A branch can be checked out in one worktree at
  a time, so this is also how parallel agents stay out of each other's way.
- **Reuse the worktree you are in**: commit or stash, then plain
  `git switch <branch>`.
- **Reach another worktree**: `gra cd <name>` prints its path.
- **See what exists**: `gra ls`.
- **Finish**: `gra done` removes the current worktree, or `gra done <name>` one
  by name. It first checks that the commits are pushed and merged, and asks
  before removing anything unfinished - so it needs a terminal to answer.
- **Every repository at once**: `gra each <command>`, or `gra each --wt
  <command>` to run in every worktree.

Do not use `git worktree add` or delete a worktree directory by hand here: gra
picks the name and the place, and `gra done` is what knows whether the work in
a worktree is safe to throw away.
