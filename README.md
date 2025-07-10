# Github DB

Create a database storing information from Github REST API about repositories, issues, and pull requests, ....

## Install

```bash
pip install .[fancy]
```

Optional dependencies:
- `fancy`: for fancy output
- `mysql`: for MySQL support
- `postgres`: for PostgreSQL support
- `docs` for documentation generation
- `test` for testing
- `pre-commit` for pre-commit hooks (enforced in CI for contributing)
- `release` for release management

## Usage

**TOKEN**: Set the environment variable `GITHUB_TOKEN` to your GitHub personal access token with the necessary permissions.

Enable autocomplete (run or add this to your `.bashrc` or venv activation script):

```bash
eval "$(_EB_GH_CLI_COMPLETE=bash_source eb_gh_cli)"
```

### Database initialization

Run the following to initialize the database and/or apply new migrations:

```bash
eb_gh_cli migrate
```

### Subcommands

- `fetch`: Fetch data from GitHub and store it in the database.
- `show`: Display information from the database.
- `stats`: Show statistics about the data in the database.
- `eb`: Show statistics specific to EasyBuild repos

Use `--help` and tab completion to explore commands.

### Examples

- Adding a new repository (this one) to the DB:

  ```bash
  eb_gh_cli fetch gh-repo Crivella/eb_gb
  ```

- Sync Issue/PRs from a repository:

  ```bash
  eb_gh_cli fetch sync-repo Crivella/eb_gb
  ```

- Show number of issue opened grouped by users on the repo

  ```bash
  eb_gh_cli stats repo-issue-creators
  ```
