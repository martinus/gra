# gra - Git Repo Admin

The repository administrator helps organize and manage git repositories. It creates directories
based on the clone URL in a specified root directory, and has tools for batch processing.
gra's root location can be configured in your `~/.gitconfig`, e.g. like so:

```sh
git config --global gra.root ~/git
```

A convenient alias to quickly move around the different repositories for your `~/.bashrc`
This requires the fuzzy searcher `fzf`.


```sh
alias cdg='cd $(gra ls|fzf)'
```

## clone - clone one or more remote repository

Clones one or more repository into the gra root directory. The
repository directory is created based on the URL and it is registered into
gra's database.

## each - run a command in the working directory of each repository

Runs the given command with all arguments for each repository. The working directory of each command
is its repository, and the commands can use these strings which are automatically replaced:

* `{{GRA_ROOT}}`: Replaced by gra root directory.
* `{{GRA_REPO}}`: Replaced by the full path of each repository.

Here are examples that you can try. Show short git status of each repository:

```sh
gra each git status -sb
```

Show disk usage of each repository. I use `{{GRA_REPO}}` so `du` shows the path, and the argument `-q`
to hide gra's status output:

```sh
gra -q each du -h -d0 {{GRA_REPO}}
```

## ls - list all repositories

Simply list all repositories. The list is updated automatically on each clone,
but if you add/remove repositories without the script, run `updatedb` to
update the index. This command can be helpful with e.g. fzf. Here is a handy
alias to quickly change directory into one of the repositories:

```sh
alias cdg = 'cd $(gra ls|fzf)'
```

## updatedb - crawls the gra root to update the list of repositories

Walks through the whole directory tree in the root path to find all
directories that contain a `.git` folder. These are then set as the repositories
in the database.

Usually there is no need to call that command, unless you add repositories without
the `clone` command. The repositories are then sorted and stored into `~/.config/gra.db.json`.

## root - shows repository root

Prints the root path used by gra. The path is configured in the global
`~/.gitconfig`. If not configured, the default is `~/git`. Set the
configuration with e.g.

```sh
git config --global gra.root ~/develop
```

This root folder is used as the base for all commands.

## vscode - generate list of projects for VSCode Project Manager

Requires Visual Studio Code with the Project Manager extension, available here:
https://marketplace.visualstudio.com/items?itemName=alefragnani.project-manager

This adds each repository to the project manager, with the netlocation as tag,
and last two subdirectories as a name. Existing configuration is kept as-is.


# Alternatives

* [ghq](https://github.com/x-motemen/ghq) was the main inspiration for `gra`. gra is much simpler,
  a single python file, git only, and integrates easily with VSCode.
* [rhq](https://github.com/siketyan/ghr) is another ghq clone, written in Rust, but it currently
  did not work with non github URLs.