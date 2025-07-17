"""Internal GitHub API client for the EB CLI."""
import atexit
import logging
import os

from github import Auth, Github, UnknownObjectException
from github import logger as github_logger
from github.Commit import Commit
from github.File import File
from github.Gist import Gist
from github.GistFile import GistFile
from github.GithubException import GithubException
from github.GithubObject import GithubObject
from github.Issue import Issue
from github.IssueComment import IssueComment
from github.Label import Label
from github.Milestone import Milestone
from github.NamedUser import NamedUser
from github.PullRequest import PullRequest
from github.PullRequestReview import PullRequestReview
from github.Repository import Repository

logger = logging.getLogger('gh_db')


GH_MAIN: Github = None

def get_gh_main() -> Github:
    """Retrieve the main GitHub instance."""
    global GH_MAIN

    if GH_MAIN is not None:
        return GH_MAIN

    # Replace the PYGithub logging handlers with the ones from this package to work better with rich
    for hnd in github_logger.handlers:
        github_logger.removeHandler(hnd)
    for hnd in logger.handlers:
        github_logger.addHandler(hnd)
    github_logger.setLevel(logger.level)

    github_token: str = os.environ.get('GITHUB_TOKEN', None)
    try:
        tok = Auth.Token(github_token)
    except AssertionError:
        logger.warning(
            'GITHUB_TOKEN is not set or invalid. Running as an unauthenticated user (Beware of rate-limits).'
        )
        tok = None

    GH_MAIN = Github(auth=tok)
    atexit.register(GH_MAIN.close)

    return GH_MAIN

__all__ = [
    'GH_MAIN',
    'get_gh_main',
    'Auth',
    'Commit',
    'Github',
    'File',
    'Gist',
    'GistFile',
    'GithubException',
    'UnknownObjectException',
    'GithubObject',
    'Issue',
    'IssueComment',
    'Label',
    'Milestone',
    'NamedUser',
    'PullRequest',
    'PullRequestReview',
    'Repository'
]
