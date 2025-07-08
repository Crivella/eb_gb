# pylint: skip-file
import click
import django
import django.core
import django.core.exceptions

from .. import models as m
from . import click_types as ct
from . import options as opt
from .main import eb_gh_cli


@eb_gh_cli.group()
def fetch():
    """Fetch data from GitHub."""
    pass


@fetch.command()
@opt.UPDATE_OPTION
@click.argument('gh_user', type=ct.GithubUserType(allow_new=True))
def gh_user(gh_user):
    """Create a GitHub user."""
    click.echo(f'GitHub user {gh_user.username} fetched successfully.')

@fetch.command()
@click.argument('gh_repo', type=str)
@click.option('--gh_user', type=ct.GithubUserType(allow_new=True), help='GitHub user for the repository')
def gh_repo(gh_repo, gh_user):
    """Create a GitHub repository."""
    gh_repo = m.GithubRepository.from_autocomplete_string(
        f'{gh_user.username}/{gh_repo}',
        allow_new=True,
    )
    click.echo(f'GitHub repository {gh_repo.name} fetched successfully.')

@fetch.command()
@opt.FILTERH_USER_OPTION
@opt.VERBOSE_OPTION
@click.argument('gh-repo', type=ct.GithubRepositoryType())
def prs_from_repo(gh_repo, verbose):
    """Create a pull request from a GitHub repository."""
    click.echo(f'Fetching pull requests from repository: {gh_repo.name}')
    try:
        pr_lst = m.GithubPullRequest.from_repository(gh_repo)
        click.echo(f'Pull requests fetched: {len(pr_lst)}')
        if verbose:
            for pr in pr_lst:
                click.echo(f'Pull request fetched: {pr.title} (ID: {pr.id})')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating pull request: {e}')

@fetch.command()
@opt.FILTERH_USER_OPTION
@opt.VERBOSE_OPTION
@opt.UPDATE_OPTION
@click.argument('gh-repo', type=ct.GithubRepositoryType())
def issues_from_repo(gh_repo, verbose):
    """Create issues from a GitHub repository. Note GH treats PRs as a subset of issues."""
    click.echo(f'Fetching issues from repository: {gh_repo.name}')
    try:
        issue_lst = m.GithubIssue.from_repository(gh_repo)
        click.echo(f'Issues fetched: {len(issue_lst)}')
        if verbose:
            for issue in issue_lst:
                click.echo(issue)
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating issue: {e}')

@fetch.command()
@opt.FILTERH_USER_OPTION
@opt.FILTER_REPO_OPTION
@opt.VERBOSE_OPTION
@opt.UPDATE_OPTION
@click.argument('gh_issue', type=ct.GithubIssueType(allow_new=True))
def comments_from_issue(gh_issue, verbose):
    """Create comments from a GitHub issue."""
    click.echo(f'Fetching comments for issue: {gh_issue.title}')
    try:
        comment_lst = gh_issue.get_comments()
        click.echo(f'Comments fetched: {len(comment_lst)}')
        if verbose:
            for comment in comment_lst:
                click.echo(f'Comment created: {comment.body[:100]} (ID: {comment.id} by {comment.created_by.username})')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating comment: {e}')
