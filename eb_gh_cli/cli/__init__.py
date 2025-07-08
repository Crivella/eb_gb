"""Module for the eb_gh_cli command line interface."""

try:
    import rich_click as click
except ImportError:
    import click

from . import fetch, show
from .main import eb_gh_cli
