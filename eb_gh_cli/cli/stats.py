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
from django.utils import timezone

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

def plot_pr_stats_over_time(
        query,
        fields: list[str],
        *,
        y_label: str,
        title: str = 'Stats Over Time',
        colors: list[str] = None,
        created_field: str = 'created_at',
        field_extra_query: dict = None,
        hist_fields: dict = None,
        group_by_months: int = 1,
        limit: int = None
    ):
    """Plot PR stats for a GitHub repository over time (created/merged/closed)."""
    if not HAVE_MATPLOTLIB:
        click.echo('Matplotlib is not installed, cannot plot PR stats.')
        return

    field_extra_query = field_extra_query or {}
    colors = colors or ['blue', 'green', 'red', 'orange', 'purple', 'cyan', 'magenta']

    end_date = datetime.now().date()
    if limit:
        start_date = end_date - relativedelta(months=group_by_months * limit)
    else:
        start_date = query.filter(
            **{f'{created_field}__isnull': False}
        ).aggregate(
            dmod.Min(created_field)
        )[f'{created_field}__min']
    click.echo(f'Plotting PR stats from {start_date} to {end_date}.')

    date_range = np.arange(start_date, end_date + relativedelta(months=1), dtype='datetime64[M]')
    date_bins = date_range[::group_by_months]
    date_bins = np.append(date_bins, np.datetime64(end_date, 'M') + np.timedelta64(1, 'M'))

    fields_counts = {field: [] for field in fields}
    for bs, be in zip(date_bins[:-1], date_bins[1:]):
        bs = timezone.make_aware(datetime.strptime(np.datetime_as_string(bs, unit='D'), '%Y-%m-%d'))
        be = timezone.make_aware(datetime.strptime(np.datetime_as_string(be, unit='D'), '%Y-%m-%d'))
        for field in fields:
            fields_counts[field].append(
                query.filter(
                    **{f'{field}__gte': bs, f'{field}__lt': be},
                    **field_extra_query.get(field, {})
                ).count()
            )
    fields_counts = {field: np.array(counts) for field, counts in fields_counts.items()}

    _, ax = plt.subplots(figsize=(18, 9))
    x = date_bins[:-1]  # Use left edges for plotting
    for i, field in enumerate(fields):
        ax.plot(
            x, fields_counts[field], marker='o', label=field.replace('_', ' ').title(),
            color=colors[i % len(colors)]
        )

    m = max(1, len(date_bins) // 25)
    xticks = date_bins[::-int(m)][::-1]  # Ensure right edge is included
    date_labels = [np.datetime_as_string(dt, unit='M') for dt in xticks]
    ax.set_xticks(xticks)
    ax.set_xticklabels(date_labels, rotation=80)

    if hist_fields is not None:
        diff = np.zeros_like(fields_counts[fields[0]])
        for field_name, mult in hist_fields.items():
            diff += fields_counts[field_name] * mult
        colors = ['red' if v < 0 else 'green' for v in diff]
        label = ''
        for field_name, mult in hist_fields.items():
            if label:
                label += ' + ' if mult > 0 else ' - '
            if abs(mult) != 1:
                label += f'{abs(mult)}*'
            label += field_name.replace('_', ' ').title()
        ax.bar(
            x, diff, np.timedelta64(group_by_months * 30, 'D') * 0.8,
            label=label,
            color=colors, alpha=0.5
        )
    ax.set_xlabel('Date (Year-Month)')
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.show()

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
    query = gh_repo.pull_requests
    plot_pr_stats_over_time(
        query,
        fields=['created_at', 'merged_at', 'closed_at'],
        colors=['blue', 'green', 'red'],
        field_extra_query={
            'closed_at': {'merged_at__isnull': True}
        },
        hist_fields={'created_at': 1, 'merged_at': -1, 'closed_at': -1},
        y_label='Number of PRs',
        title=f'PR Stats Over Time for {gh_repo.name}',
        group_by_months=group_by_months,
        limit=limit
    )

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
    query = gh_repo.issues.filter(is_pr=False)
    plot_pr_stats_over_time(
        query,
        fields=['created_at', 'closed_at'],
        colors=['blue', 'red'],
        hist_fields={'created_at': 1, 'closed_at': -1},
        y_label='Number of Issues',
        title=f'Issue Stats Over Time for {gh_repo.name}',
        group_by_months=group_by_months,
        limit=limit
    )
