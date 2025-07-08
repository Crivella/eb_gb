"""eb_gh_cli.cli.main"""
import django
import django.core
import django.core.exceptions
from django.core.management import call_command

from . import click


@click.group()
@click.version_option()
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
