"""Stats commands for the eb_gh_cli eb CLI."""
import re

from ... import models as m
from .. import click
from .. import click_types as ct
# from . import options as opt
from . import eb

# from django.db import models as dmod


# {data,lib,tools}[GCCcore/12.3.0] crossguid v20190529, indicators v2.3, rapidcsv v8.87
ec_pr_title_rgx = re.compile(
    r'^\{(?P<classes>[^\}]+)\}\s*\[(?P<toolchains>[^\]]+)\]\s*(?P<title>.+)?\s*$',
)


@eb.command()
@click.argument('gh_repo', type=ct.GithubRepositoryType())
@click.option('--tc-filter', type=str, help='Filter by toolchain.')
@click.option('--mclass-filter', type=str, help='Filter by module class.')
def group_open_prs(gh_repo: m.GithubRepository, tc_filter: str = None, mclass_filter: str = None):
    """Show the top open PRs for a GitHub repository."""
    q = m.GithubPullRequest.objects
    q = q.filter(is_closed=False, is_merged=False, repository=gh_repo)

    pr_lst = q.all()

    toolchain = {}
    unclassified = []

    for pr in pr_lst:
        match = ec_pr_title_rgx.match(pr.title)
        if match:
            classes = match.group('classes').split(',')
            toolchains = match.group('toolchains').split(',')
            # title = match.group('title')

            for tc in toolchains:
                tc = tc.strip()
                if not tc:
                    continue
                ptr = toolchain.setdefault(tc, {})
                for cls in classes:
                    cls = cls.strip()
                    if not cls:
                        continue
                    lst = ptr.setdefault(cls, [])
                    lst.append(pr)
        else:
            unclassified.append(pr)

    itab = '|   '
    ilvl = 0
    for tc, ptr in toolchain.items():
        if tc_filter and tc_filter not in tc:
            continue
        click.echo(f'{itab * ilvl}{tc}')
        ilvl += 1
        for mclass, lst in ptr.items():
            if mclass_filter and mclass_filter not in mclass:
                continue
            click.echo(f'{itab * ilvl}{mclass}')
            ilvl += 1
            for pr in lst:
                click.echo(f'{itab * ilvl}{pr})')
            ilvl -= 1
        ilvl -= 1

    if unclassified:
        click.echo(f'{itab * ilvl}Unclassified PRs:')
        ilvl += 1
        click.echo(f'{itab * ilvl}Total: {len(unclassified)}')
        ilvl -= 1

    click.echo(f'{itab * ilvl}Total PRs: {len(pr_lst)}')
