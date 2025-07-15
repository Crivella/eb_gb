"""Module for handling progress bars in the CLI."""

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

def progress_bar(
        iterable, total=None,
        description=None, **kwargs
    ):
    """Create a progress bar using rich."""
    if not HAVE_RICH:
        return iterable

    ACTIVE_PROGRESS.start()

    return ACTIVE_PROGRESS.track(
        iterable, total=total,
        description=description, **kwargs
    )

def progress_clean_tasks():
    """Cleanup the progress bar."""
    if not HAVE_RICH:
        return
    for task in ACTIVE_PROGRESS.tasks:
        if task.completed == task.total or task.total is None:
            ACTIVE_PROGRESS.remove_task(task.id)
        # else:
        #     ACTIVE_PROGRESS.console.print(
        #         f'Task {task.id} ({task.description}) is not completed: {task.completed}/{task.total}'
        #     )
