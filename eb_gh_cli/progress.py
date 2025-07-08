"""Module for handling progress bars in the CLI."""

HAVE_RICH = False

try:
    from rich.progress import track
except ImportError:
    pass
else:
    HAVE_RICH = True

def progress_bar(iterable, total=None, description=None, **kwargs):
    """Create a progress bar using rich."""
    if not HAVE_RICH:
        return iterable

    return track(
        iterable, total=total, description=description,
        **kwargs
    )
