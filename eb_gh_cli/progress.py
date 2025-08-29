"""Module for handling progress bars in the CLI."""
import time

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

def delayed_iter(iterable, delay=None):  # pylint: disable=inconsistent-return-statements
    """Add a delay to fetching elements of an iterable"""
    if delay is None:
        return iterable
    for item in iterable:
        yield item
        time.sleep(delay)

def progress_bar(
        iterable, total=None,
        delay=0.5,
        description=None, **kwargs
    ):
    """Create a progress bar using rich."""
    if not HAVE_RICH:
        return iterable

    ACTIVE_PROGRESS.start()

    iterable = delayed_iter(iterable=iterable, delay=delay)

    return ACTIVE_PROGRESS.track(
        iterable, total=total,
        description=description, **kwargs
    )

def progress_clean_tasks():
    """Cleanup the progress bar."""
    if not HAVE_RICH:
        return
    for task in ACTIVE_PROGRESS.tasks:
        if task.completed == task.total or (task.total is None and task.id > 0):
            ACTIVE_PROGRESS.remove_task(task.id)
        # else:
        #     ACTIVE_PROGRESS.console.print(
        #         f'Task {task.id} ({task.description}) is not completed: {task.completed}/{task.total}'
        #     )
