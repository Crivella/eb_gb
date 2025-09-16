"""Fetch commands for the eb_gh_cli CLI."""
from django.db import connection
from django.db import models as dmod

from .. import models as m
from ..progress import progress_bar
from . import click
from . import click_types as ct
from .main import maint


@maint.command()
@click.option('--gh-repo', type=ct.GithubRepositoryType(allow_new=False), help='GitHub repository to fetch gists from.')
def prune_commits_unreferenced(gh_repo: m.GithubRepository = None):
    """Prune commits that are not referenced by any Github PR, File, child_commits objects."""
    q = m.GithubCommit.objects
    if gh_repo:
        q = q.filter(repository=gh_repo)

    q = q.annotate(
        pr_count=dmod.Count('pull_requests'),
        file_count=dmod.Count('files'),
        child_commit_count=dmod.Count('child_commits'),
    )

    q = q.filter(
        dmod.Q(pr_count=0),
        dmod.Q(file_count=0),
        dmod.Q(child_commit_count=0),
    )

    total = q.count()
    if total == 0:
        click.echo('No unreferenced commits found.')
        return
    click.echo(f'Found {total} unreferenced commits to prune.')
    click.echo('First 5 commits:')
    for commit in q[:5].all():
        click.echo(f'- {commit.url} ({commit.sha})')

    if not click.confirm('Do you want to proceed?', default=False):
        click.echo('Aborting.')
        return

    to_delete = list(q.all())
    for commit in progress_bar(to_delete, total=total, description='Pruning commits', delay=None):
        commit.delete()

@maint.command()
@click.option('--gh-repo', type=ct.GithubRepositoryType(allow_new=False), help='GitHub repository to fetch gists from.')
@click.option(
    '--regex', type=str, default=r'^Merge branch ',
    help='Regex to match commit messages to prune. Default: "^Merge branch "'
)
def prune_commits_merge(regex: str, gh_repo: m.GithubRepository = None):
    """Prune commits that are not referenced by any Github PR, File, child_commits objects."""
    q = m.GithubCommit.objects
    if gh_repo:
        q = q.filter(repository=gh_repo)

    q = q.annotate(
        file_count=dmod.Count('files'),
    )

    q = q.filter(
        dmod.Q(file_count__gte=20),
        dmod.Q(message__regex=regex),
    )

    total = q.count()
    if total == 0:
        click.echo('No unreferenced commits found.')
        return
    click.echo(f'Found {total} merge commits to prune with regex "{regex}".')
    click.echo('First 5 commits:')
    for commit in q[:5].all():
        click.echo(f'- {commit.url} ({commit.sha})')

    if not click.confirm('Do you want to proceed?', default=False):
        click.echo('Aborting.')
        return

    to_delete = list(q.all())
    for commit in progress_bar(to_delete, total=total, description='Pruning commits', delay=None):
        commit.delete()

@maint.command()
def prune_files_unreferenced():
    """Prune files that do not belong to any pull request or commit."""
    q = m.GithubFile.objects
    q = q.filter(
        pull_request__isnull=True,
        commit__isnull=True,
    )

    total = q.count()
    if total == 0:
        click.echo('No unreferenced files found.')
        return
    click.echo(f'Found {total} unreferenced files to prune.')
    click.echo('First 5 files:')
    for f in q[:5].all():
        click.echo(f'- {f.url} ({f.filename})')
    if not click.confirm('Do you want to proceed?', default=False):
        click.echo('Aborting.')
        return

    raise NotImplementedError('File pruning not implemented yet.')

@maint.command()
def vacuum():
    """Vacuum the database."""
    with connection.cursor() as cursor:
        cursor.execute('VACUUM;')
    click.echo('Database vacuumed.')
