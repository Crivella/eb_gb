"""Module for the eb_gh_cli eb command line interface."""

from ..main import eb_gh_cli


@eb_gh_cli.group()
def eb():
    """Main entry point for the eb_gh_cli eb CLI."""

# Avoid circular imports by importing after defining the group
from .stats import group_open_prs  # pylint: disable=wrong-import-position

__all__ = [
    'eb',
    'group_open_prs'
]
