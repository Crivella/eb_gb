"""Stats commands for the eb_gh_cli CLI."""
from datetime import datetime

from django.db import models as dmod

from .. import models as m
from . import click
from . import click_types as ct
from . import options as opt
from .main import stats


def user_pr_issue_stats(qparam: str, repository: m.GithubRepository, since: datetime = None):
    """Get user PR and issue stats."""
    q = m.GithubUser.objects
    cnt_flt = dmod.Q(**{f'{qparam}__repository': repository})
    if since:
        key = qparam.split('_')[0]
        key += '_at'
        cnt_flt &= dmod.Q(**{f'{qparam}__{key}__gte': since})
    q = q.annotate(
        count=dmod.Count(
            qparam,
            filter=cnt_flt
        ),
    )
    q = q.filter(
        dmod.Q(count__gt=0)
    )
    q = q.order_by('-count')

    users = q.all()

    descr = qparam.replace('_', ' ')
    if not users:
        click.echo(f'No users found for `{descr}` in `{repository}`.')
    else:
        click.echo(f'Top users for repository {repository.name}:')
        for user in users:
            click.echo(f'{user.username:>25s} : {user.count:>7d}  {descr}')

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@opt.SINCE_OPTION
def repo_pr_mergers(gh_repo: m.GithubRepository, since):
    """Show the top PR mergers for a GitHub repository."""
    click.echo(f'Fetching PR mergers for {gh_repo.name} since {since} {type(since)}.')
    user_pr_issue_stats('merged_pull_requests', gh_repo, since=since)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@opt.SINCE_OPTION
def repo_pr_creators(gh_repo: m.GithubRepository, since):
    """Show the top PR creators for a GitHub repository."""
    user_pr_issue_stats('created_pull_requests', gh_repo, since=since)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@opt.SINCE_OPTION
def repo_issue_creators(gh_repo: m.GithubRepository, since):
    """Show the top issue creators for a GitHub repository."""
    user_pr_issue_stats('created_issues', gh_repo, since=since)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@opt.SINCE_OPTION
def repo_issue_closers(gh_repo: m.GithubRepository, since):
    """Show the top issue closers for a GitHub repository."""
    user_pr_issue_stats('closed_issues', gh_repo, since=since)
