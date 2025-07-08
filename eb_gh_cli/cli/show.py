"""Show commands for the eb_gh_cli CLI."""
from . import click
from . import click_types as ct
from . import options as opt
from .main import show


@show.command()
@opt.FILTER_USER_OPTION
@click.argument('gh_repo', type=ct.GithubRepositoryType())
def gh_repo(repo):
    """Show a GitHub repository."""
    click.echo(f'GitHub repository: {repo}')

@show.command()
@opt.FILTER_USER_OPTION
@opt.FILTER_REPO_OPTION
@click.argument('gh_issue', type=ct.GithubIssueType())
def gh_issue(issue):
    """Show a GitHub issue."""
    click.echo(f'GitHub issue: {issue}')
    click.echo(f'Issue number: {issue.number}')
    click.echo(f'Title: {issue.title}')
    click.echo(f'Description: {issue.body}')
    click.echo(f'Created by: {issue.created_by.username}')
    click.echo(f'Closed by: {issue.closed_by.username if issue.closed_by else 'N/A'}')
    # click.echo(f'Assignee: {gh_issue.assignee.username if gh_issue.assignee else "N/A"}')

@show.command()
@opt.FILTER_USER_OPTION
@opt.FILTER_REPO_OPTION
@click.argument('gh_pr', type=ct.GithubPullRequestType())
def gh_pr(pr):
    """Show a Github Pull Request."""
    click.echo(f'GitHub Pull Request: {pr}')
    click.echo(f'Pull Request number: {pr.number}')
    click.echo(f'Title: {pr.title}')
    click.echo(f'Description: {pr.body}')
    click.echo(f'Created by: {pr.created_by.username}')
    # click.echo(f'Closed by: {gh_pr.closed_by.username if gh_pr.closed_by else "N/A"}')
    click.echo(f'Merged by: {pr.merged_by.username if pr.merged_by else 'N/A'}')
