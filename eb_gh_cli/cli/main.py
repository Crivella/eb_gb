# pylint: skip-file
import click
import django
import django.core
import django.core.exceptions
from django.core.management import call_command


@click.group()
@click.version_option()
def eb_gh_cli():
    pass

@eb_gh_cli.command()
def migrate():
    """Run database migrations."""
    click.echo('Running migrations...')
    try:
        call_command('migrate')
        click.echo('Migrations completed successfully.')
    except django.core.exceptions.ImproperlyConfigured as e:
        click.echo(f'Error during migration: {e}')

# Import groups here to ensure the CLI is aware of them
from .fetch import fetch
from .show import show
