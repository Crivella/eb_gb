"""Stats commands for the eb_gh_cli CLI."""
from collections import defaultdict
from datetime import datetime
from datetime import timezone as dt_timezone

from dateutil.relativedelta import relativedelta

try:
    import matplotlib.pyplot as plt
    import numpy as np
    HAVE_MATPLOTLIB = True
except ImportError:
    plt = None
    HAVE_MATPLOTLIB = False

from django.db import models as dmod
from django.utils import timezone as dj_timezone

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
@click.option('--limit', type=int, default=None, help='Limit of the plot in days. Flatten lifetimes > limit to limit.')
@opt.SINCE_OPTION
@opt.UPTO_OPTION
@click.option('--highlight-labels', type=str, help='Comma-separated list of labels to highlight in the plot.')
@click.option('--fraction', is_flag=True, help='Plot fraction of PRs instead of absolute counts.')
def repo_pr_lifetime(
        gh_repo: m.GithubRepository,
        limit: int = None,
        since = None, upto = None,
        highlight_labels: str = None,
        fraction: bool = False
    ):
    """Make an histogram of PR lifetimes for a GitHub repository. For Open PRs, the lifetime is calculated until now."""
    if not HAVE_MATPLOTLIB:
        click.echo('Matplotlib is not installed, cannot plot PR stats.')
        return
    query = gh_repo.pull_requests.filter(
        created_at__isnull=False
    )
    if since:
        query = query.filter(created_at__gte=since)
    if upto:
        query = query.filter(created_at__lte=upto)

    hl_labels = set()
    if highlight_labels:
        hl_labels = set(l.strip() for l in highlight_labels.split(',') if l.strip())

    click.echo(f'Highlighting labels (and their cross-product): {hl_labels}')

    label_data = {}
    num_low = defaultdict(int)
    avg_low = defaultdict(int)
    num_tot = 0
    avg_lifetime = 0
    for pr in query.all():
        pr: m.GithubPullRequest
        pr_labels = set(l.name for l in pr.labels.all())
        ptr_labels = tuple(sorted(pr_labels.intersection(hl_labels)))
        if pr.merged_at:
            lifetime = (pr.merged_at - pr.created_at).total_seconds() / (3600.0 * 24)
        elif pr.closed_at:
            lifetime = (pr.closed_at - pr.created_at).total_seconds() / (3600.0 * 24)
        else:
            lifetime = (datetime.now(dt_timezone.utc) - pr.created_at).total_seconds() / (3600.0 * 24)

        avg_lifetime += lifetime
        num_tot += 1
        ptr_labels = ptr_labels or ('other',)
        if limit is not None and lifetime > limit:
            lifetime = limit
        else:
            avg_low[ptr_labels] += lifetime
            num_low[ptr_labels] += 1

        label_data.setdefault(ptr_labels, []).append(lifetime)

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.set_xlabel('PR Lifetime (days)')
    ax.set_ylabel(f'{'Fraction' if fraction else 'Number'} of PRs')

    num_bins = int(max(max(_) for _ in label_data.values()) // 1 + 1 if label_data else 10)

    label_data = dict(sorted(label_data.items(), key=lambda item: item[0], reverse=True))

    colors = ['blue', 'green', 'red', 'orange', 'purple', 'cyan', 'magenta']

    ax.hist(
        list(label_data.values()),
        bins=num_bins,
        color=colors[:len(label_data)],
        density=fraction,
        alpha=0.7,
        label=[f'Labels: {label} (n={len(data)})' for label, data in label_data.items()]
    )

    for i,label in enumerate(label_data):
        if num_low[label]:
            ax.axvline(
                avg_low[label] / num_low[label],
                color=colors[i % len(colors)], linestyle='dashed', linewidth=1,
                label=f'Avg Lifetime (d<={limit}) ({label}): {avg_low[label] / num_low[label]:.2f} days'
            )

    if num_tot:
        ax.axvline(
            avg_lifetime / num_tot,
            color='black', linestyle='dashed', linewidth=1,
            label=f'Avg Lifetime: {avg_lifetime / num_tot:.2f} days'
        )

    fig.legend()

    title_str = f'PR Lifetime `{gh_repo.name}`'
    if since:
        title_str += f' since {since.strftime('%Y-%m-%d')}'
    if upto:
        title_str += f' upto {upto.strftime('%Y-%m-%d')}'
    ax.set_title(title_str)

    plt.tight_layout()
    plt.show()

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
        bs = dj_timezone.make_aware(datetime.strptime(np.datetime_as_string(bs, unit='D'), '%Y-%m-%d'))
        be = dj_timezone.make_aware(datetime.strptime(np.datetime_as_string(be, unit='D'), '%Y-%m-%d'))
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
