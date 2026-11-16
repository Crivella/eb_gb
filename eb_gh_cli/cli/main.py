"""eb_gh_cli.cli.main"""
import os

import django
import django.core
import django.core.exceptions
from django.core.management import call_command

from . import click


def environ_setter(env_var):
    def setter(ctx, param, value):
        os.environ[env_var] = value
        return value
    return setter


@click.group()
@click.version_option()
@click.option(
    '--root-dir',
    type=click.Path(file_okay=False, dir_okay=True),
    default=os.path.expanduser('~/.gh_db'),
    expose_value=False,
    callback=environ_setter('GH_DB_ROOT'),
    help='Root directory for the GitHub database and file storage',
)
@click.option(
    '--database-name',
    type=click.STRING,
    default='gh_db.sqlite3',
    expose_value=False,
    callback=environ_setter('DATABASE_NAME'),
    help='Name of the SQLite database file',
)
def eb_gh_cli():
    """Main entry point for the eb_gh_cli CLI."""

@eb_gh_cli.command()
def migrate():
    """Run database migrations."""
    click.echo('Running migrations...')
    try:
        call_command('migrate')
        click.echo('Migrations completed successfully.')
    except django.core.exceptions.ImproperlyConfigured as e:
        click.echo(f'Error during migration: {e}')

@eb_gh_cli.group()
def fetch():
    """Fetch data from GitHub."""


@eb_gh_cli.group()
def maint():
    """Perform maintenance operations on the database."""

@eb_gh_cli.group()
def show():
    """Show  data from GitHub."""

@eb_gh_cli.group()
def stats():
    """Stats  data from GitHub."""

__all__ = [
    'eb_gh_cli',
    'migrate',
    'fetch',
    'show'
]
