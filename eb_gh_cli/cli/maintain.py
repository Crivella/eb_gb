"""Fetch commands for the eb_gh_cli CLI."""
import logging
from functools import wraps

from django.conf import settings
from django.db import connection
from django.db import models as dmod
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .. import models as m
from ..progress import progress_bar
from ..storage import DOSStorage, Storage
from . import click
from . import click_types as ct
from .main import maint

logger = logging.getLogger('gh_db')

STORAGE: Storage = m.GithubFile._meta.get_field('content').storage


def delete_file_if_unreferenced(file_hash: str) -> bool:
    """Delete a file from storage if it is not referenced by any GithubFile object.

    Returns True if the file was deleted, False otherwise.
    """
    q = m.GithubFile.objects.filter(dmod.Q(content=file_hash) | dmod.Q(patch=file_hash))
    if not q.exists():
        STORAGE.delete(file_hash)
        logger.debug(f'Deleting unreferenced file with hash {file_hash} from storage.')
        return True
    return False


def file_deletion_watcher(func):
    """Decorator to watch for GithubGile deletions to also remove files from storage if unreferenced."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        deleted_files_hases = set()

        @receiver(post_delete, sender=m.GithubFile)
        def on_file_delete(sender, instance: m.GithubFile, **kwargs):  # pylint: disable=unused-argument
            deleted_files_hases.add(instance.content.name)
            deleted_files_hases.add(instance.patch.name)

        result = func(*args, **kwargs)

        logger.info(f'Deleted {len(deleted_files_hases)} files from pruned commits.')
        if deleted_files_hases:
            deleted_files = 0
            for file_hash in progress_bar(deleted_files_hases, description='Cleaning up files', delay=None):
                deleted_files += delete_file_if_unreferenced(file_hash)

            logger.info(f'Deleted {deleted_files} unreferenced files from storage.')
            if isinstance(STORAGE, DOSStorage):
                logger.info('Repacking `DOSStorage` storage container...')
                with STORAGE.container as container:
                    container.repack()
                logger.info('DONE')

        post_delete.disconnect(on_file_delete, sender=m.GithubFile)
        return result

    return wrapper


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
        logger.info('No unreferenced commits found.')
        return

    logger.info(f'Found {total} unreferenced commits to prune.')
    if not click.confirm('Do you want to proceed?', default=False):
        logger.info('Aborting.')
        return

    for commit in progress_bar(q.all(), total=total, description='Pruning commits', delay=None):
        commit.delete()

@maint.command()
@click.option('--gh-repo', type=ct.GithubRepositoryType(allow_new=False), help='GitHub repository to fetch gists from.')
@click.option(
    '--regex', type=str, default=r'^Merge branch ',
    help='Regex to match commit messages to prune. Default: "^Merge branch "'
)
@file_deletion_watcher
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
        logger.info('No unreferenced commits found.')
        return
    logger.info(f'Found {total} merge commits to prune with regex "{regex}".')

    if not click.confirm('Do you want to proceed?', default=False):
        logger.info('Aborting.')
        return

    for commit in progress_bar(q.all(), total=total, description='Pruning commits', delay=None):
        commit.delete()

@maint.command()
@file_deletion_watcher
def prune_files_unreferenced():
    """Prune files that do not belong to any pull request or commit."""
    q = m.GithubFile.objects
    q = q.filter(
        pull_request__isnull=True,
        commit__isnull=True,
    )

    total = q.count()
    if total == 0:
        logger.info('No unreferenced files found.')
        return
    logger.info(f'Found {total} unreferenced files to prune.')
    if not click.confirm('Do you want to proceed?', default=False):
        logger.info('Aborting.')
        return

    for file in progress_bar(q.all(), total=total, description='Pruning files', delay=None):
        file.delete()

@maint.command()
def storage_maintenance():
    """Perform maintenance on the storage backend."""
    if isinstance(STORAGE, DOSStorage):
        logger.info('Performing `DOSStorage` storage container...')
        with STORAGE.container as container:
            steps = ['repacking', 'packing loose files', 'cleaning storage']
            before = container.get_total_size()
            for step in progress_bar(steps, description='Storage maintenance', delay=None):
                logger.info(f'--- {step}')
                if step == 'repacking':
                    container.repack()
                elif step == 'packing loose files':
                    container.pack_all_loose(compress=True)
                elif step == 'cleaning storage':
                    container.clean_storage(vacuum=True)
            after = container.get_total_size()

        before_tot = before.total_size_packfiles_on_disk + before.total_size_loose
        after_tot = after.total_size_packfiles_on_disk + after.total_size_loose
        logger.info(f'Storage size before: {before_tot / (1024**2):.2f} MiB')
        logger.info(f'Storage size after:  {after_tot / (1024**2):.2f} MiB')
    else:
        logger.info('Storage backend does not support maintenance operations.')

@maint.command()
def vacuum():
    """Vacuum the database."""
    if settings.DATABASE_ENGINE.endswith('sqlite3'):
        click.echo('Vacuuming SQLite database...')
        with connection.cursor() as cursor:
            cursor.execute('VACUUM;')
    else:
        click.echo('Database vacuuming is only supported for SQLite databases.')
