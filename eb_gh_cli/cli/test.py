# pylint: skip-file
import os

import click
import django
import django.core
import django.core.exceptions
from click.shell_completion import CompletionItem
from django.core.management import call_command
from django.db import models
from django.db.models import Q

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
    query_param_convert = lambda _, x: x
    model_class: models.Model = None

    user_filter = None

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

        update = getattr(ctx, 'hidden_params', {}).get('update', False)

        value = self.query_param_convert(value)
        try:
            res = self.model_class.from_dct(
                {
                    self.query_param_name: value
                },
                allow_new=self.allow_new,
                update=update
            )
        except ValueError as e:
            self.fail(f'Item {self.model_class.__name__}<{value}> does not exists and cannot be created', param, ctx)
        except Exception as e:
            self.fail(f'Error while converting {self.model_class.__name__}<{value}>: {e}', param, ctx)

        return res

    def shell_complete(self, ctx: click.Context, param: click.Parameter, incomplete: str):
        """Provide shell completion for DjangoModelType."""
        hidden_params = getattr(ctx, 'hidden_params', {})
        q = self.model_class.objects
        kwargs = {
            f'{self.query_param_name}__startswith': incomplete
        }

        q = q.filter(**kwargs)
        if (gh_user := hidden_params.get('gh_user', None)) and self.user_filter:
            q = q.filter(self.__class__.user_filter(gh_user))

        choices = q.all()
        return [CompletionItem(getattr(obj, self.query_param_name), help=str(obj)) for obj in choices]

    def __repr__(self):
        return f'{self.__class__.__name__}({self.model_class.__name__}, {self.query_param_name})'

class GithubUserType(DjangoModelType):
    query_param_name = 'username'
    query_param_convert = lambda _, x: str(x)
    model_class = m.GithubUser

class GithubRepositoryType(DjangoModelType):
    query_param_name = 'name'
    query_param_convert = lambda _, x: str(x)
    model_class = m.GithubRepository

    user_filter = lambda gh_user: Q(owner=gh_user)
    # user_filter = lambda gh_user: Q(owner=gh_user) | Q(owner__username=gh_user.username)

class GithubIssueType(DjangoModelType):
    query_param_name = 'title'
    query_param_convert = lambda _, x: str(x)
    model_class = m.GithubIssue

def register_hidden_param(ctx, param, value):
    if not hasattr(ctx, 'hidden_params'):
        ctx.hidden_params = {}
    ctx.hidden_params[param.name] = value

UPDATE_OPTION = click.option(
    '--update',
    is_flag=True,
    expose_value=False,
    callback=register_hidden_param,
    help='Update existing GitHub Object if it exists'
)

GH_USER_OPTION = click.option(
    '-u', '--gh-user',
    type=GithubUserType(),
    help='GitHub user to filter repositories',
    expose_value=False,
    callback=register_hidden_param
)

@click.group()
def eb_gh_cli():
    pass

@eb_gh_cli.group()
def fetch():
    """Fetch data from GitHub."""
    pass

@eb_gh_cli.group()
def show():
    """Fetch data from GitHub."""
    pass

@show.command()
@GH_USER_OPTION
@click.argument('gh_repo', type=GithubRepositoryType())
def gh_repo(gh_repo):
    """Show a GitHub repository."""
    click.echo(f'GitHub repository: {gh_repo}')

@fetch.command()
@UPDATE_OPTION
@click.argument('gh_user', type=GithubUserType(allow_new=True))
def gh_user(gh_user):
    """Create a GitHub user."""
    # click.echo(f'Got GitHub user: {gh_user.username}')
    click.echo(f'GitHub user {gh_user.username} fetched successfully.')

@fetch.command()
@click.argument('gh_repo', type=str)
@click.option('--gh_user', type=GithubUserType(allow_new=True), help='GitHub user for the repository')
def gh_repo(gh_repo, gh_user):
    """Create a GitHub repository."""
    gh_repo = m.GithubRepository.from_dct({
        'name': gh_repo,
        'owner': gh_user,
    }, allow_new=True)
    click.echo(f'GitHub repository {gh_repo.name} fetched successfully.')

@fetch.command()
@GH_USER_OPTION
@click.argument('gh-repo', type=GithubRepositoryType())
def prs_from_repo(gh_repo):
    """Create a pull request from a GitHub repository."""
    click.echo(f'Fetching pull requests from repository: {gh_repo.name}')
    try:
        pr_lst = m.GithubPullRequest.from_repository(gh_repo)
        click.echo(f'Pull requests fetched: {len(pr_lst)}')
        # for pr in pr_lst:
        #     click.echo(f'Pull request fetched: {pr.title} (ID: {pr.id})')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating pull request: {e}')

@fetch.command()
@GH_USER_OPTION
@click.argument('gh-repo', type=GithubRepositoryType())
def issues_from_repo(gh_repo):
    """Create issues from a GitHub repository."""
    click.echo(f'Fetching issues from repository: {gh_repo.name}')
    try:
        issue_lst = m.GithubIssue.from_repository(gh_repo)
        click.echo(f'Issues fetched: {len(issue_lst)}')
        # for issue in issue_lst:
        #     click.echo(f'Issue created: {issue.title} (ID: {issue.id} by {issue.created_by.username})')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating issue: {e}')

@fetch.command()
@click.argument('gh_issue', type=GithubIssueType(allow_new=True))
def comments_from_issue(gh_issue):
    """Create comments from a GitHub issue."""
    click.echo(f'Fetching comments for issue: {gh_issue.title}')
    try:
        comment_lst = gh_issue.get_comments()
        click.echo(f'Comments fetched: {len(comment_lst)}')
        # for comment in comment_lst:
        #     click.echo(f'Comment created: {comment.body[:100]} (ID: {comment.id} by {comment.created_by.username})')
    except django.core.exceptions.ValidationError as e:
        click.echo(f'Error creating comment: {e}')


@eb_gh_cli.command()
def migrate():
    """Run database migrations."""
    click.echo('Running migrations...')
    try:
        call_command('migrate')
        click.echo('Migrations completed successfully.')
    except django.core.exceptions.ImproperlyConfigured as e:
        click.echo(f'Error during migration: {e}')
