"""Stats commands for the eb_gh_cli CLI."""
from datetime import datetime

from dateutil.relativedelta import relativedelta

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
        limit: int = None,
        only_open: bool = False
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
    if only_open:
        cnt_flt &= dmod.Q(**{f'{qparam}__is_closed': False})

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
@click.option('--only-open', is_flag=True, help='Limit the number of users shown.')
@opt.SINCE_OPTION
@opt.UPTO_OPTION
def repo_pr_creators(gh_repo: m.GithubRepository, since, upto, limit, only_open):
    """Show the top PR creators for a GitHub repository."""
    user_pr_issue_stats('created_pull_requests', gh_repo, since=since, upto=upto, limit=limit, only_open=only_open)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--limit', type=int, default=None, help='Limit the number of users shown.')
@click.option('--only-open', is_flag=True, help='Limit the number of users shown.')
@opt.SINCE_OPTION
@opt.UPTO_OPTION
def repo_issue_creators(gh_repo: m.GithubRepository, since, upto, limit, only_open):
    """Show the top issue creators for a GitHub repository."""
    user_pr_issue_stats('created_issues', gh_repo, since=since, upto=upto, limit=limit, only_open=only_open)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--limit', type=int, default=None, help='Limit the number of users shown.')
@opt.SINCE_OPTION
def repo_issue_closers(gh_repo: m.GithubRepository, since, upto, limit):
    """Show the top issue closers for a GitHub repository."""
    user_pr_issue_stats('closed_issues', gh_repo, since=since, upto=upto, limit=limit)

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--group-by-months', type=click.INT, default=1, help='Group stats by number of months.')
@click.option('--limit', type=click.INT, default=None, help='Limit the number of data points shown.')
def pr_plot(
        gh_repo: m.GithubRepository,
        group_by_months: int,
        limit: int = None
    ):
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

    start_date = min(min(_) for _ in [created_dates, merged_dates, closed_dates] if _)
    end_date = max(max(_) for _ in [created_dates, merged_dates, closed_dates] if _)
    if limit:
        start_date = max(end_date - relativedelta(months=group_by_months * limit), start_date)
    click.echo(f'Plotting PR stats from {start_date} to {end_date}.')

    date_range = np.arange(start_date, end_date, dtype='datetime64[M]')
    date_bins = date_range[::group_by_months]
    date_bins = np.append(date_bins, np.datetime64(end_date, 'M') + np.timedelta64(1, 'M'))

    created_counts, _ = np.histogram(created_dates, bins=date_bins)
    merged_counts, _ = np.histogram(merged_dates, bins=date_bins)
    closed_counts, _ = np.histogram(closed_dates, bins=date_bins)

    _, ax = plt.subplots(figsize=(18, 9))
    x = date_bins[:-1]  # Use left edges for plotting

    ax.plot(x, created_counts, marker='o', label='Created', color='blue')
    ax.plot(x, merged_counts, marker='o', label='Merged', color='green')
    ax.plot(x, closed_counts, marker='o', label='Closed', color='red')

    m = max(1, len(date_bins) // 25)
    xticks = date_bins[::-int(m)][::-1]  # Ensure right edge is included
    date_labels = [np.datetime_as_string(dt, unit='M') for dt in xticks]
    ax.set_xticks(xticks)
    ax.set_xticklabels(date_labels, rotation=80)

    # Also plot histogram of differences between created and merged/closed
    diff = created_counts - (merged_counts + closed_counts)
    colors = ['red' if v < 0 else 'green' for v in diff]
    ax.bar(
        x, diff, np.timedelta64(group_by_months, 'M') * 0.8,
        label='Created - (Merged + Closed)', color=colors, alpha=0.5
    )

    ax.set_xlabel('Date (Year-Month)')
    ax.set_ylabel('Number of PRs')
    ax.set_title(f'PR Stats Over Time for {gh_repo.name}')
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.show()

@stats.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--group-by-months', type=click.INT, default=1, help='Group stats by number of months.')
@click.option('--limit', type=click.INT, default=None, help='Limit the number of data points shown.')
def issue_plot(
        gh_repo: m.GithubRepository,
        group_by_months: int,
        limit: int = None
    ):
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

    start_date = min(min(_) for _ in [created_dates, closed_dates] if _)
    end_date = max(max(_) for _ in [created_dates, closed_dates] if _)
    if limit:
        start_date = max(end_date - relativedelta(months=group_by_months * limit), start_date)
    click.echo(f'Plotting PR stats from {start_date} to {end_date}.')

    date_range = np.arange(start_date, end_date, dtype='datetime64[M]')
    date_bins = date_range[::group_by_months]
    date_bins = np.append(date_bins, np.datetime64(end_date, 'M') + np.timedelta64(1, 'M'))

    created_counts, _ = np.histogram(created_dates, bins=date_bins)
    closed_counts, _ = np.histogram(closed_dates, bins=date_bins)

    _, ax = plt.subplots(figsize=(18, 9))
    x = date_bins[:-1]  # Use left edges for plotting

    ax.plot(x, created_counts, marker='o', label='Created', color='blue')
    ax.plot(x, closed_counts, marker='o', label='Closed', color='red')

    m = max(1, len(date_bins) // 25)
    xticks = date_bins[::-int(m)][::-1]  # Ensure right edge is included
    date_labels = [np.datetime_as_string(dt, unit='M') for dt in xticks]
    ax.set_xticks(xticks)
    ax.set_xticklabels(date_labels, rotation=80)

    # Also plot histogram of differences between created and merged/closed
    diff = created_counts - closed_counts
    colors = ['red' if v < 0 else 'green' for v in diff]
    ax.bar(
        x, diff, np.timedelta64(group_by_months, 'M') * 0.8,
        label='Created - Closed', color=colors, alpha=0.5
    )

    ax.set_xlabel('Date (Year-Month)')
    ax.set_ylabel('Number of Issues')
    ax.set_title(f'Issues Stats Over Time for {gh_repo.name}')
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.show()
