"""Fetch commands for the eb_gh_cli CLI."""
import logging
import re
import time
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


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    lst = list(lst)  # Ensure lst is a list
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


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


def filter_gists(ids: set[str]) -> set[str]:
    """Filter gists by their IDs, removing those that already exist in the database."""
    existing_gists = set()
    for chunk in chunks(ids, 1000):
        # Use a set to avoid duplicates
        existing_gists.update(m.GithubGist.objects.filter(gist_id__in=chunk).values_list('gist_id', flat=True))
    ids = ids - existing_gists

    return ids

def fetch_gists(
    ids: set[str],
    iss_map: dict = None, cmt_map: dict = None, gst_map: dict = None,
    delay: float = 2,
    force: bool = False, files: bool = True
) -> list[m.GithubGist]:
    """Fetch gists by their IDs, optionally using maps for issues, comments, and source gists."""
    iss_map = iss_map or {}
    cmt_map = cmt_map or {}
    gst_map = gst_map or {}

    res = []
    for gist_id in progress_bar(ids, description=f'Fetching {len(ids)} gists from issue-comments'):
        issue = iss_map.get(gist_id, None)
        comment = cmt_map.get(gist_id, None)
        source_gist = gst_map.get(gist_id, None)
        try:
            gist = m.GithubGist.from_id(gist_id, issue=issue, comment=comment, source_gist=source_gist, update=force)
            if files:
                gist.fetch_files()
        except gh_api.UnknownObjectException as e:
            logger.warning(f'{issue} : {comment.url} : Gist `{gist_id}` not found: {e}')
        except django.core.exceptions.ValidationError as e:
            logger.error(f'{issue} : {comment.url} : Error fetching gist `{gist_id}`: {e}')
        except Exception as e:
            logger.error(f'{issue} : {comment.url} : Unexpected error fetching gist `{gist_id}`: {e}', exc_info=True)
        else:
            res.append(gist)
            time.sleep(delay)
    return res

@fetch.command()
@click.argument('gh-repo', type=ct.GithubRepositoryType())
@opt.SINCE_OPTION
@opt.SINCE_NUMBER_OPTION
@click.option('--files/--no-files', is_flag=True, default=True, help='Fetch files for commits.')
@click.option('--force', '-f', is_flag=True, help='Force updating gists that are already downloaded')
def gists_from_issuecomments(
    gh_repo: m.GithubRepository,
    since: datetime = None,
    since_number: int = None,
    files: bool = True,
    force: bool = True,
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

    ids = set()
    ids_issue_map = {}
    ids_comment_map = {}
    for issue in query.all():
        num_issues += 1
        for comment in issue.comments.all():
            num_comments += 1
            for mch in GIST_RGX.finditer(comment.body):
                gist_id = mch.group('id')
                ids.add(gist_id)
                ids_issue_map[gist_id] = issue
                ids_comment_map[gist_id] = comment

    since_str = f">={since.strftime('%Y-%m-%d')}" if since else 'all'
    click.echo(f'{gh_repo} ({since_str}) : {num_issues} issues : {num_comments} comments : {len(ids)} gists.')

    if not force:
        before = len(ids)
        ids = filter_gists(ids)
        click.echo(f'Filtered {before - len(ids)} gists that already exist in the database.')

    res = fetch_gists(ids, iss_map=ids_issue_map, cmt_map=ids_comment_map, force=force, files=files)

    num_failed = len(ids) - len(res)
    click.echo(f'Fetched {len(res)} gists from {gh_repo} ({since_str}) with {num_failed} failed/not-found.')

@fetch.command()
# @click.argument('gh-repo', type=ct.GithubRepositoryType())
@click.option('--gh-repo', type=ct.GithubRepositoryType(allow_new=True), help='GitHub repository to fetch gists from.')
@opt.SINCE_OPTION
@click.option('--files/--no-files', is_flag=True, default=True, help='Fetch files for commits.')
@click.option('--force', '-f', is_flag=True, help='Force updating gists that are already downloaded')
def gists_from_gists(
    gh_repo: m.GithubRepository = None,
    since: datetime = None,
    files: bool = True,
    force: bool = True,
):
    """Find gists URLs in commit messages and fetch them."""

    repo_msg = 'all repositories' if gh_repo is None else f"repository {gh_repo.name}"
    click.echo(f'Fetching gists from commits from {repo_msg}...')
    query = m.GithubGist.objects
    if gh_repo:
        query = query.filter(source_issue__repository=gh_repo)
    if since:
        query = query.filter(updated_at__gte=since)

    ids = set()
    ids_gist_map = {}
    for gist in query.all():
        for file in gist.files.all():
            fp = file.content
            if not fp.name:
                continue
            fp.seek(0)
            content = fp.read().decode('utf-8')
            for mch in GIST_RGX.finditer(content):
                gist_id = mch.group('id')
                ids.add(gist_id)
                ids_gist_map[gist_id] = gist

    since_str = f">={since.strftime('%Y-%m-%d')}" if since else 'all'
    repo_msg = f'{gh_repo}' if gh_repo else 'All repositories'
    click.echo(f'{repo_msg} ({since_str}) : {len(ids)} gists found in files.')

    if not force:
        before = len(ids)
        ids = filter_gists(ids)
        click.echo(f'Filtered {before - len(ids)} gists that already exist in the database.')

    res = fetch_gists(ids, gst_map=ids_gist_map, force=force, files=files)

    num_failed = len(ids) - len(res)
    click.echo(f'Fetched {len(res)} gists from {gh_repo} ({since_str}) with {num_failed} failed/not-found.')
