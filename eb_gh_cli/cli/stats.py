"""Stats commands for the eb_gh_cli CLI."""
from datetime import datetime

try:
    import matplotlib.pyplot as plt
    import numpy as np
    HAVE_MATPLOTLIB = True
except ImportError:
    plt = None
    HAVE_MATPLOTLIB = False

from django.db import models as dmod

from .. import models as m
from . import click
from . import click_types as ct
from . import options as opt
from .main import stats


def user_pr_issue_stats(
        qparam: str, repository: m.GithubRepository,
        since: datetime = None, upto: datetime = None,
        limit: int = None
    ):
    """Get user PR and issue stats."""
    q = m.GithubUser.objects
    cnt_flt = dmod.Q(**{f'{qparam}__repository': repository})
    if since:
        key = qparam.split('_')[0]
        key += '_at'
        cnt_flt &= dmod.Q(**{f'{qparam}__{key}__gte': since})
    if upto:
        key = qparam.split('_')[0]
        key += '_at'
        cnt_flt &= dmod.Q(**{f'{qparam}__{key}__lte': upto})
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
    if limit:
        q = q[:limit]

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
@click.option('--limit', type=int, default=None, help='Limit the number of users shown.')
@opt.SINCE_OPTION
@opt.UPTO_OPTION
def repo_pr_mergers(gh_repo: m.GithubRepository, since, upto, limit):
    """Show the top PR mergers for a GitHub repository."""
    click.echo(f'Fetching PR mergers for {gh_repo.name} since {since} {type(since)}.')
    user_pr_issue_stats('merged_pull_requests', gh_repo, since=since, upto=upto, limit=limit)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--limit', type=int, default=None, help='Limit the number of users shown.')
@opt.SINCE_OPTION
@opt.UPTO_OPTION
def repo_pr_creators(gh_repo: m.GithubRepository, since, upto, limit):
    """Show the top PR creators for a GitHub repository."""
    user_pr_issue_stats('created_pull_requests', gh_repo, since=since, upto=upto, limit=limit)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--limit', type=int, default=None, help='Limit the number of users shown.')
@opt.SINCE_OPTION
@opt.UPTO_OPTION
def repo_issue_creators(gh_repo: m.GithubRepository, since, upto, limit):
    """Show the top issue creators for a GitHub repository."""
    user_pr_issue_stats('created_issues', gh_repo, since=since, upto=upto, limit=limit)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--limit', type=int, default=None, help='Limit the number of users shown.')
@opt.SINCE_OPTION
def repo_issue_closers(gh_repo: m.GithubRepository, since, upto, limit):
    """Show the top issue closers for a GitHub repository."""
    user_pr_issue_stats('closed_issues', gh_repo, since=since, upto=upto, limit=limit)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
def pr_plot(gh_repo: m.GithubRepository):
    """Plot PR stats for a GitHub repository over time (created/merged/closed)."""
    if not HAVE_MATPLOTLIB:
        click.echo('Matplotlib is not installed, cannot plot PR stats.')
        return
    q = gh_repo.pull_requests.all()
    if not q:
        click.echo(f'No pull requests found for repository {gh_repo.name}.')
        return
    click.echo(f'Found {len(q)} pull requests for repository {gh_repo.name}.')

    created_dates = [pr.created_at.date() for pr in q]
    merged_dates = [pr.merged_at.date() for pr in q if pr.merged_at]
    closed_dates = [pr.closed_at.date() for pr in q if pr.closed_at and not pr.merged_at]

    created_dates_counts = {}
    for date in created_dates:
        date_str = date.strftime('%Y-%m')
        created_dates_counts[date_str] = created_dates_counts.get(date_str, 0) + 1
    merged_dates_counts = {}
    for date in merged_dates:
        date_str = date.strftime('%Y-%m')
        merged_dates_counts[date_str] = merged_dates_counts.get(date_str, 0) + 1
    closed_dates_counts = {}
    for date in closed_dates:
        date_str = date.strftime('%Y-%m')
        closed_dates_counts[date_str] = closed_dates_counts.get(date_str, 0) + 1

    all_dates = set(created_dates_counts.keys()) | set(merged_dates_counts.keys()) | set(closed_dates_counts.keys())
    all_dates = sorted(all_dates)
    created_counts = [created_dates_counts.get(date, 0) for date in all_dates]
    merged_counts = [merged_dates_counts.get(date, 0) for date in all_dates]
    closed_counts = [closed_dates_counts.get(date, 0) for date in all_dates]

    # Plot with 1 month bins from starting to ending month
    _, ax = plt.subplots(figsize=(18, 9))
    x = np.arange(len(all_dates))
    ax.plot(x, created_counts, marker='o', label='Created', color='blue')
    ax.plot(x, merged_counts, marker='o', label='Merged', color='green')
    ax.plot(x, closed_counts, marker='o', label='Closed', color='red')
    ax.set_xticks(x[::4])
    ax.set_xticklabels(all_dates[::4], rotation=80)

    # Also plot histogram of differences between created and merged/closed
    diff = np.array(created_counts) - (np.array(merged_counts) + np.array(closed_counts))
    colors = ['red' if v < 0 else 'green' for v in diff]
    ax.bar(x, diff, label='Created - (Merged + Closed)', color=colors, alpha=0.5)

    ax.set_xlabel('Date (Year-Month)')
    ax.set_ylabel('Number of PRs')
    ax.set_title(f'PR Stats Over Time for {gh_repo.name}')
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.show()

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
def issue_plot(gh_repo: m.GithubRepository):
    """Plot PR stats for a GitHub repository over time (created/merged/closed)."""
    if not HAVE_MATPLOTLIB:
        click.echo('Matplotlib is not installed, cannot plot PR stats.')
        return
    q = gh_repo.issues.filter(is_pr=False).all()
    if not q:
        click.echo(f'No pull requests found for repository {gh_repo.name}.')
        return

    created_dates = [pr.created_at.date() for pr in q]
    closed_dates = [pr.closed_at.date() for pr in q if pr.closed_at]

    created_dates_counts = {}
    for date in created_dates:
        date_str = date.strftime('%Y-%m')
        created_dates_counts[date_str] = created_dates_counts.get(date_str, 0) + 1
    closed_dates_counts = {}
    for date in closed_dates:
        date_str = date.strftime('%Y-%m')
        closed_dates_counts[date_str] = closed_dates_counts.get(date_str, 0) + 1

    all_dates = set(created_dates_counts.keys()) | set(closed_dates_counts.keys())
    all_dates = sorted(all_dates)
    created_counts = [created_dates_counts.get(date, 0) for date in all_dates]
    closed_counts = [closed_dates_counts.get(date, 0) for date in all_dates]

    # Plot with 1 month bins from starting to ending month
    _, ax = plt.subplots(figsize=(18, 9))
    x = np.arange(len(all_dates))
    ax.plot(x, created_counts, marker='o', label='Created', color='blue')
    ax.plot(x, closed_counts, marker='o', label='Closed', color='red')
    ax.set_xticks(x[::4])
    ax.set_xticklabels(all_dates[::4], rotation=80)

    # Also plot histogram of differences between created and merged/closed
    diff = np.array(created_counts) - np.array(closed_counts)
    colors = ['red' if v < 0 else 'green' for v in diff]
    ax.bar(x, diff, label='Created - Closed', color=colors, alpha=0.5)

    ax.set_xlabel('Date (Year-Month)')
    ax.set_ylabel('Number of Issues')
    ax.set_title(f'Issues Stats Over Time for {gh_repo.name}')
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.show()
