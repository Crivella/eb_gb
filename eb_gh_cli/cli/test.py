# pylint: skip-file
import os

import click
import django
import django.core
import django.core.exceptions
from click.shell_completion import CompletionItem
from django.core.management import call_command
from django.db import models

# from ..models import ABC
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eb_gh_cli.settings')
django.setup()

from logging import getLogger

from .. import models as m

logger = getLogger(__name__)

class DjangoModelType(click.ParamType):
    """
    A custom Click parameter type for Django model instances.
    This type can be used to retrieve a model instance by its primary key.
    """
    query_param_name: str = None
    query_param_convert: str = None
    model_class: models.Model = None

    def __init__(self, allow_new: bool = False):
        if self.model_class is None:
            raise ValueError('model_class must be set for DjangoModelType')
        if self.query_param_name is None:
            raise ValueError('query_param must be set for DjangoModelType')
        if self.query_param_convert is None:
            raise ValueError('query_param_convert must be set for DjangoModelType')
        super().__init__()

        self.allow_new = allow_new

    def convert(self, value, param, ctx):
        res = None

        value = self.query_param_convert(value)
        try:
            res = self.model_class.from_dct({
                self.query_param_name: value
            }, allow_new=self.allow_new)
        except ValueError as e:
            self.fail(f'Item {self.model_class.__name__}<{value}> does not exists and cannot be created', param, ctx)
            raise e

        return res

    def shell_complete(self, ctx: click.Context, param: click.Parameter, incomplete: str):
        """Provide shell completion for DjangoModelType."""
        q = self.model_class.objects
        kwargs = {
            f'{self.query_param_name}__startswith': incomplete
        }
        q = q.filter(**kwargs)
        choices = q.all()
        return [CompletionItem(getattr(obj, self.query_param_name), help=str(obj)) for obj in choices]

    def __repr__(self):
        return f'{self.__class__.__name__}({self.model_class.__name__}, {self.query_param_name})'

class GithubUserType(DjangoModelType):
    query_param_name = 'username'
    query_param_convert = lambda _, x: str(x)
    model_class = m.GithubUser

@click.group()
def eb_gh_cli():
    pass

# @eb_gh_cli.command()
# @click.option(
#     '-v',
#     '--verbose',
#     is_flag=True,
#     help='Enable verbose logging',
#     )
# @click.argument('gh_user', type=ABCType())
# def thisisatest(verbose, gh_user):
#     click.echo(f'This is a test command with and verbose={verbose}')
#     # from django.contrib.auth import get_user_model
#     # User = get_user_model()

#     click.echo(f'You passed ABC: {gh_user.name} with description: {gh_user.description}')

#     # all_abcs = m.ABC.objects.all()
#     # click.echo(f'Found {all_abcs.count()} users in the database:')
#     # for abc in all_abcs:
#     #     click.echo(f' - {abc.name}: {abc.description}')

@eb_gh_cli.command()
@click.argument('gh_user', type=GithubUserType(allow_new=True))
def gh_user(gh_user):
    """Create a GitHub user."""
    click.echo(f'Got GitHub user: {gh_user.username}')
    try:
        gh_user.save()
        click.echo(f'GitHub user {gh_user.username} created successfully.')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating GitHub user: {e}')


@eb_gh_cli.command()
def migrate():
    """Run database migrations."""
    click.echo('Running migrations...')
    try:
        call_command('migrate')
        click.echo('Migrations completed successfully.')
    except django.core.exceptions.ImproperlyConfigured as e:
        click.echo(f'Error during migration: {e}')
