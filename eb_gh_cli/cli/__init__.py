"""Module for the eb_gh_cli command line interface."""
# pylint: skip-file

try:
    import click as original_click
    import rich_click as click
except ImportError:
    import click
    import click as original_click
else:
    from rich.traceback import install
    install(
        show_locals=True,
        suppress=[click, original_click],
    )

from . import fetch, show, stats
from .eb_cmd import *
from .main import eb_gh_cli
