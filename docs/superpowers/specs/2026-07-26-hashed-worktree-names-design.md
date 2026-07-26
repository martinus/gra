# Worktree names derived from the repository

## Problem

`gra` picks worktree names at random from a fixed word pool. Working on the
same repositories from several computers therefore produces different names for
the same work: `oans` is `hare` on the laptop and `tide` on the desktop. Names
are the address of a worktree - in `gra cd wolf`, in tmux window names, in
conversation - so an address that changes per machine is worth less than one
that does not.

## Goal

The same repository gets the same worktree name on every machine, without any
shared state between them. Divergence is acceptable when two machines have
genuinely different repositories competing for one name.

## Design

### Identity

`worktree_identity(container)` returns the string that is hashed:

1. `owner/repo` parsed from `remote.origin.url` with the existing
   `parse_repo_url()` - so `git@github.com:martinus/oans.git` and
   `https://github.com/martinus/oans.git` both give `martinus/oans`, and a
   machine cloning over SSH agrees with one cloning over HTTPS,
2. the repository name alone when the URL has no owner segment (a local path
   clone),
3. the container's directory name when there is no origin at all.

Every repository therefore has an identity, not just GitHub-shaped ones.

### Candidates

`name_candidates(identity)` sorts the entire word pool by the SHA-256 of
`identity#word`: a shuffle of every name, private to that repository, best
first. Because each name appears exactly once, the list can neither repeat
itself nor run out.

The hash must be SHA-256, not Python's built-in `hash()`: `hash()` is
randomized per process for strings, so it would not be stable across two runs
on one machine, let alone two computers.

### Picking

`pick_worktree_name(root, identity)` returns the first name in that order not
taken by any worktree anywhere under the gra root. There is no stored counter:
every pick starts at the front, so a repository's k-th worktree lands on its
k-th name as a consequence of the earlier ones being taken.

A name being taken by this repository's own earlier worktree and by an
unrelated repository are the same case, handled by the same rule. That single
rule is the whole collision resolution.

Running off the end of the list means every name is in use, which keeps the
existing failure:

    all worktree names are taken; run 'gra clean' or 'gra done' first

### What this promises

Two machines that clone the same repository get the same first worktree name,
without knowing about each other. They diverge only when another repository on
one of them has already claimed a contested word - so divergence is
order-dependent, and it shifts one repository rather than resetting the rest.

Removing a worktree frees its word, and the next `gra work` in that repository
reclaims it. Names are stable under churn, not only at clone time. Existing
worktrees are never renamed.

## Testing

* the same identity produces the same name in two separate processes,
* SSH and HTTPS clones of one repository produce the same name,
* two independent gra roots, standing in for two machines, agree,
* a taken first candidate falls through to the second, deterministically,
* a repository without an origin is still deterministic,
* an exhausted word pool still fails with the existing message.

## Documentation

"Random" becomes wrong everywhere it is asserted, which is more places than
the README: its intro, `work` section and uniqueness paragraph, but also the
script's module docstring, the `clone` and `work` help texts that users
actually read, and two function docstrings. All of them are reworded to
describe names as derived from the repository and identical on every machine.
