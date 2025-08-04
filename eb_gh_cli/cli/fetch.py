"""Fetch commands for the eb_gh_cli CLI."""
import logging
import re
from datetime import datetime

import django
import django.core
import django.core.exceptions

from .. import gh_api
from .. import models as m
from ..progress import progress_bar, progress_clean_tasks
from . import click
from . import click_types as ct
from . import options as opt
from .main import fetch

GIST_RGX = re.compile(r'https?://gist\.github\.com(?P<user>/[^/\n]+)?/(?P<id>[a-z0-9]+)(?:\#file-(?P<file>[^/\n]+))?')

logger = logging.getLogger('gh_db')


@fetch.command()
@opt.UPDATE_OPTION
@click.argument('gh_user', type=ct.GithubUserType(allow_new=True))
def gh_user(user):
    """Create a GitHub user."""
    click.echo(f'GitHub user {user.username} fetched successfully.')

@fetch.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType(allow_new=True))
def gh_repo(gh_repo):
    """Create a GitHub repository."""
    click.echo(f'GitHub repository {gh_repo.name} fetched successfully.')

@fetch.command()
@opt.FILTER_USER_OPTION
@opt.VERBOSE_OPTION
@click.argument('gh-repo', type=ct.GithubRepositoryType())
def prs_from_repo(gh_repo, verbose):
    """Create a pull request from a GitHub repository."""
    try:
        pr_lst = m.GithubPullRequest.from_repository(gh_repo)
        click.echo(f'Pull requests fetched: {len(pr_lst)}')
        if verbose:
            for pr in pr_lst:
                click.echo(f'Pull request fetched: {pr.title} (ID: {pr.id})')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating pull request: {e}')

@fetch.command()
@opt.FILTER_USER_OPTION
@opt.VERBOSE_OPTION
@opt.UPDATE_OPTION
@click.argument('gh-repo', type=ct.GithubRepositoryType())
def issues_from_repo(gh_repo, verbose):
    """Create issues from a GitHub repository. Note GH treats PRs as a subset of issues."""
    try:
        issue_lst = m.GithubIssue.from_repository(gh_repo)
        click.echo(f'Issues fetched: {len(issue_lst)}')
        if verbose:
            for issue in issue_lst:
                click.echo(issue)
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating issue: {e}')

@fetch.command()
@opt.FILTER_USER_OPTION
@opt.FILTER_REPO_OPTION
@opt.VERBOSE_OPTION
@opt.UPDATE_OPTION
@click.argument('gh_issue', type=ct.GithubIssueType(allow_new=True))
def comments_from_issue(gh_issue, verbose):
    """Create comments from a GitHub issue."""
    try:
        comment_lst = gh_issue.get_comments()
        click.echo(f'Comments fetched: {len(comment_lst)}')
        if verbose:
            for comment in comment_lst:
                click.echo(f'Comment created: {comment.body[:100]} (ID: {comment.id} by {comment.created_by.username})')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating comment: {e}')

@fetch.command()
@opt.FILTER_USER_OPTION
# @opt.SINCE_OPTION
@opt.SINCE_NUMBER_OPTION
@click.option('--update-open', type=click.IntRange(min=1), help='Update open issues and PRs.')
@click.option('--prs/--no-prs', is_flag=True, default=True, help='Fetch PRs as well.')
@click.option('--commits/--no-commits', is_flag=True, default=True, help='Fetch commits for PRs.')
@click.option(
    '--comments/--no-comments', is_flag=True, default=True,
    help='Fetch comments for issues and reviews for PRs.'
)
@click.option('--files/--no-files', is_flag=True, default=True, help='Fetch files for PRs and commits.')
@click.argument('gh-repo', type=ct.GithubRepositoryType())
def sync_repo(
    gh_repo: m.GithubRepository,
    # since: datetime = None,
    since_number: int = None,
    update_open: int = None,
    prs: bool = True,
    commits: bool = True,
    comments: bool = True,
    files: bool = True
):
    """Synchronize a GitHub repository Issue and PRs with the database."""
    try:
        issue_lst = m.GithubIssue.from_repository(
            gh_repo,
            # since=since,
            since_number=since_number,
            do_prs=prs, do_comments=comments, do_files=files, do_commits=commits
        )
        click.echo(f'New Issues fetched: {len(issue_lst)}')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating issue: {e}')

    if update_open:
        # Avoid updating issues that were just fetched
        numbers = [issue.number for issue in issue_lst]

        q = gh_repo.issues
        q = q.filter(is_closed=False)
        q = q.filter(number__gte=update_open)
        q = q.exclude(number__in=numbers)
        open_issues = q.all()
        open_issues = progress_bar(
            open_issues,
            description=f'Updating {len(open_issues)} open issues',
        )
        updated = []
        for issue in open_issues:
            new = issue.update()
            if new:
                updated.append(new)
            progress_clean_tasks()
        click.echo(f'Updated {len(updated)} open issues.')

        if prs:
            q = gh_repo.pull_requests
            q = q.filter(is_merged=False, is_closed=False)
            q = q.filter(number__gte=update_open)
            q = q.exclude(number__in=numbers)
            open_prs = q.all()
            open_prs = progress_bar(
                open_prs,
                description=f'Updating {len(open_prs)} open pull requests',
            )
            updated = []
            for pr in open_prs:
                new = pr.update()
                if new:
                    updated.append(new)
                progress_clean_tasks()
            click.echo(f'Updated {len(updated)} open pull requests.')

@fetch.command()
@click.argument('gh-repo', type=ct.GithubRepositoryType())
@opt.SINCE_OPTION
@opt.SINCE_NUMBER_OPTION
@click.option('--files/--no-files', is_flag=True, default=True, help='Fetch files for commits.')
def gists_from_issuecomments(
    gh_repo: m.GithubRepository,
    since: datetime = None,
    since_number: int = None,
    files: bool = True,
):
    """Find gists URLs in commit messages and fetch them."""

    click.echo(f'Fetching gists from commits in repository {gh_repo.name}...')
    num_issues = 0
    num_comments = 0
    query = gh_repo.issues
    if since:
        query = query.filter(updated_at__gte=since)
    if since_number:
        query = query.filter(number__gte=since_number)

    ids = []
    for issue in query.all():
        num_issues += 1
        for comment in issue.comments.all():
            num_comments += 1
            for mch in GIST_RGX.finditer(comment.body):
                gist_id = mch.group('id')
                ids.append((issue, comment, gist_id))

    since_str = f">={since.strftime('%Y-%m-%d')}" if since else 'all'
    click.echo(f'{gh_repo} ({since_str}) : {num_issues} issues : {num_comments} comments : {len(ids)} gists.')

    for issue, comment, gist_id in progress_bar(
        ids,
        description=f'Fetching {len(ids)} gists from issue-comments',
    ):
        try:
            gist = m.GithubGist.from_id(gist_id, issue=issue, comment=comment)
            if files:
                gist.fetch_files()
        except gh_api.UnknownObjectException as e:
            logger.warning(f'{issue} : {comment.url} : Gist `{gist_id}` not found: {e}')
        except django.core.exceptions.ValidationError as e:
            logger.error(f'{issue} : {comment.url} : Error fetching gist `{gist_id}`: {e}')
        except Exception as e:
            logger.error(f'{issue} : {comment.url} : Unexpected error fetching gist `{gist_id}`: {e}', exc_info=True)
