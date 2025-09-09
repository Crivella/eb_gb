"""Module for handling progress bars in the CLI."""
import time
from contextlib import contextmanager

HAVE_RICH = False

try:
    from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                               SpinnerColumn, TextColumn, TimeElapsedColumn,
                               TimeRemainingColumn)
except ImportError:
    ACTIVE_PROGRESS = None
else:
    import atexit
    ACTIVE_PROGRESS: Progress = Progress(
        SpinnerColumn(),
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )
    atexit.register(ACTIVE_PROGRESS.stop)
    HAVE_RICH = True

def delayed_iter(iterable, delay=None):
    """Add a delay to fetching elements of an iterable"""
    for item in iterable:
        yield item
        time.sleep(delay)

PROGRESS_BAR_LEVEL = 0

def set_progress_bar_level(level: int):
    """Set the global progress bar level."""
    global PROGRESS_BAR_LEVEL
    PROGRESS_BAR_LEVEL = level

@contextmanager
def progress_bar_level_inc(clean_tasks: bool = True):
    """Context manager to increase the progress bar level."""
    global PROGRESS_BAR_LEVEL
    PROGRESS_BAR_LEVEL += 1
    try:
        yield
    finally:
        if clean_tasks:
            progress_clean_tasks()
        PROGRESS_BAR_LEVEL -= 1

def progress_bar(
        iterable, total=None,
        delay=0.5,
        description=None, **kwargs
    ):
    """Create a progress bar using rich."""
    if not HAVE_RICH:
        return iterable

    ACTIVE_PROGRESS.start()

    kwargs['total'] = total or len(iterable)

    if delay is not None and delay > 0:
        iterable = delayed_iter(iterable=iterable, delay=delay)

    description = '| ' * PROGRESS_BAR_LEVEL + (description or 'Working')

    return ACTIVE_PROGRESS.track(iterable, description=description, **kwargs)

def progress_clean_tasks():
    """Cleanup the progress bar."""
    if not HAVE_RICH:
        return
    for task in ACTIVE_PROGRESS.tasks:
        if task.completed == task.total:
            ACTIVE_PROGRESS.remove_task(task.id)
        # else:
        #     ACTIVE_PROGRESS.console.print(
        #         f'Task {task.id} ({task.description}) is not completed: {task.completed}/{task.total}'
        #     )
