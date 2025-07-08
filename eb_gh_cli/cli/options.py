# pylint: skip-file
import click

from . import click_types as ct


def register_hidden_param(ctx, param, value):
    if not hasattr(ctx, 'hidden_params'):
        ctx.hidden_params = {}
    ctx.hidden_params[param.name] = value

VERBOSE_OPTION = click.option(
    '-v', '--verbose',
    is_flag=True,
    help='Enable verbose output'
)

UPDATE_OPTION = click.option(
    '--update',
    is_flag=True,
    expose_value=False,
    callback=register_hidden_param,
    help='Update existing GitHub Object if it exists'
)

FILTERH_USER_OPTION = click.option(
    '-u', '--gh-user',
    type=ct.GithubUserType(),
    help='GitHub user',
    expose_value=False,
    callback=register_hidden_param
)

FILTER_REPO_OPTION = click.option(
    '-r', '--gh-repo',
    type=ct.GithubRepositoryType(),
    help='GitHub repository',
    expose_value=False,
    callback=register_hidden_param
)
