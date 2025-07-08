"""Show commands for the eb_gh_cli CLI."""
from . import click
from . import click_types as ct
from . import options as opt
from .main import show


@show.command()
@opt.FILTER_USER_OPTION
@click.argument('gh_repo', type=ct.GithubRepositoryType())
def gh_repo(gh_repo):
    """Show a GitHub repository."""
    click.echo(f'GitHub repository: {gh_repo}')

@show.command()
@opt.FILTER_USER_OPTION
@opt.FILTER_REPO_OPTION
@click.argument('gh_issue', type=ct.GithubIssueType())
def gh_issue(gh_issue):
    """Show a GitHub issue."""
    click.echo(f'GitHub issue: {gh_issue}')
    click.echo(f'Issue number: {gh_issue.number}')
    click.echo(f'Title: {gh_issue.title}')
    click.echo(f'Description: {gh_issue.body}')
    click.echo(f'Created by: {gh_issue.created_by.username}')
    click.echo(f'Closed by: {gh_issue.closed_by.username if gh_issue.closed_by else 'N/A'}')
    # click.echo(f'Assignee: {gh_issue.assignee.username if gh_issue.assignee else "N/A"}')

@show.command()
@opt.FILTER_USER_OPTION
@opt.FILTER_REPO_OPTION
@click.argument('gh_pr', type=ct.GithubPullRequestType())
def gh_pr(gh_pr):
    """Show a Github Pull Request."""
    click.echo(f'GitHub Pull Request: {gh_pr}')
    click.echo(f'Pull Request number: {gh_pr.number}')
    click.echo(f'Title: {gh_pr.title}')
    click.echo(f'Description: {gh_pr.body}')
    click.echo(f'Created by: {gh_pr.created_by.username}')
    # click.echo(f'Closed by: {gh_pr.closed_by.username if gh_pr.closed_by else "N/A"}')
    click.echo(f'Merged by: {gh_pr.merged_by.username if gh_pr.merged_by else 'N/A'}')
