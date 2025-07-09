"""GitHub-related models for Django application."""
import logging
import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Generic, TypeVar

import django
import github
# import github.Branch
import github.GithubObject
import github.Issue
import github.IssueComment
import github.Label
import github.Milestone
import github.NamedUser
import github.PullRequest
import github.PullRequestComment
import github.PullRequestReview
import github.Repository
from django.db import models
from github import Auth, Github

from .progress import progress_bar

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', None)

T = TypeVar('T', bound='GithubMixin')
# https://stackoverflow.com/questions/61146406/
O = TypeVar('O', bound=github.GithubObject.GithubObject)

logger = logging.getLogger('gh_db')

try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eb_gh_cli.settings')
    django.setup()
except RuntimeError as e:
    pass

class NODEFAULT:
    """A sentinel value to indicate that a default value is not provided."""

class ColObjMap:
    """
    A class to represent a mapping between model fields and GitHub object attributes.
    This is used to define how to extract data from GitHub objects when creating or updating Django models.
    """
    def __init__(self, column: str, param: str, default: Any = NODEFAULT, converter: Callable = None):
        self.column = column
        self.param = param
        self.default = default
        self.converter = converter if converter else lambda x: x

    def __iter__(self):
        yield self.column
        yield self.param
        yield self.default
        yield self.converter


def with_github(func):
    """
    Decorator to provide a GitHub instance to the decorated function.
    The function must accept a `tok` parameter of type `Auth.Token`.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not GITHUB_TOKEN:
            raise ValueError(
                'GITHUB_TOKEN environment variable is not set. Please set it to use GitHub-related features.'
            )
        tok = Auth.Token(GITHUB_TOKEN)
        with Github(auth=tok) as gh:
            return func(*args, gh=gh, **kwargs)
    return wrapper


class GithubMixin(models.Model, Generic[O]):
    """Mixin for common fields used in GitHub-related models."""
    gh_id = models.BigIntegerField(unique=True, null=True, help_text='GitHub ID of the object')
    url = models.URLField(max_length=255, blank=True, null=True)

    internal_created_at = models.DateTimeField(auto_now_add=True)
    internal_updated_at = models.DateTimeField(auto_now=True)

    id_key: str = 'id'
    obj_col_map: list[ColObjMap] = []

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gh_obj = None

    class DoesNotSupportDirectCreation(Exception):
        """
        Exception raised when a model does not support direct creation from a dictionary.
        This is used to enforce that subclasses implement the `create_from_dct` method.
        """

    @classmethod
    def from_autocomplete_string(
            cls: T, autocomplete_string: str,
            allow_new: bool = False,
            update: bool = False
        ) -> T:
        """
        Create or update an instance from a dictionary.
        If the instance does not exist and allow_new is True, create a new instance.
        """
        dct = cls.autocomplete_string_to_dct(autocomplete_string)
        q = cls.objects.filter(**dct)
        cnt = q.count()
        if cnt > 1:
            raise ValueError(
                f"Multiple {cls.__name__} instances found with {dct}. Use a more specific filter."
            )
        if cnt == 1:
            if update:
                res = cls.create_from_dct(dct, update=update)
            else:
                res = q.first()
        else:
            if not allow_new:
                raise ValueError(f"{cls.__name__} with {dct} does not exist and allow_new is False.")
            res = cls.create_from_dct(dct)
        return res

    def get_autocomplete_string(self) -> str:
        """
        Return a string representation for autocomplete purposes.
        This should be overridden in subclasses to provide meaningful information.
        """
        raise self.DoesNotSupportDirectCreation(
            f"{self.__class__.__name__}.get_autocomplete_string must be implemented."
        )

    @classmethod
    def autocomplete_string_to_dct(cls, autocomplete_string: str) -> dict:
        """
        Convert an autocomplete string to a dictionary.
        This should be overridden in subclasses to parse the string correctly.
        """
        raise cls.DoesNotSupportDirectCreation(
            f"{cls.__class__.__name__}.autocomplete_string_to_dct must be implemented."
        )

    @classmethod
    def filter_autocomplete_string(cls: T, autocomplete_string: str) -> list[T]:
        """
        Filter instances based on an autocomplete string.
        This method should be overridden in subclasses to handle specific filtering logic.
        """
        raise cls.DoesNotSupportDirectCreation(
            f"{cls.__class__.__name__}.filter_autocomplete_string must be implemented."
        )

    @classmethod
    def create_from_dct(cls: T, dct: dict, *, gh: Github = None, update: bool = False) -> T:
        """
        Create a new instance from the provided keyword arguments.
        This method should be overridden in subclasses to handle specific creation logic.
        """
        raise cls.DoesNotSupportDirectCreation(f"{cls.__name__}.create_from_dct must be implemented.")

    @classmethod
    def create_from_obj(cls: T, obj, **kwargs) -> T:
        """
        Create an instance from a GitHub object.
        This method should be overridden in subclasses to handle specific object creation logic.
        """
        update = kwargs.pop('update', False)
        foreign = kwargs.pop('foreign', None) or {}
        if kwargs:
            raise ValueError(f"Unexpected keyword arguments: {kwargs}")
        func = cls.objects.update_or_create if update else cls.objects.get_or_create

        defaults = {}
        for column, param, default, converter in cls.obj_col_map:
            value = obj
            for key in param.split('.'):
                value = getattr(value, key, default)
                if value is NODEFAULT:
                    raise ValueError(f"Parameter '{param}' is required for {cls.__name__} creation.")
            value = converter(value) if converter else value
            defaults[column] = value

        id_key = cls.id_key.split('.')
        gh_id = obj
        for key in id_key:
            gh_id = getattr(gh_id, key)

        for key, val in foreign.items():
            defaults[key] = val

        res, created = func(
            gh_id=gh_id,
            defaults=defaults
        )
        if created:
            logger.debug(f"Created new {cls.__name__} instance: {res}")
        elif update:
            logger.debug(f"Updated existing {cls.__name__} instance: {res}")
        return res

    @property
    def gh_obj(self) -> O:
        """Retrieve the GitHub object associated with this instance."""
        if self._gh_obj is None:
            self._gh_obj = self.get_gh_obj()
        return self._gh_obj

    @with_github
    def get_gh_obj(self, *, gh: Github = None):
        """
        Fetch the GitHub object associated with this instance.
        This method should be overridden in subclasses to fetch the appropriate GitHub object.
        """
        raise self.DoesNotSupportDirectCreation(f"{self.__class__.__name__}.get_gh_obj must be implemented.")

class GithubUser(GithubMixin[github.NamedUser.NamedUser]):
    """Model representing a GitHub user."""
    username = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=False, blank=True, null=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    obj_col_map = [
        ColObjMap('username', 'login'),
        ColObjMap('email', 'email', None),
        ColObjMap('url', 'html_url'),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
    ]

    def __str__(self):
        return self.username

    @classmethod
    @with_github
    def create_from_dct(cls: T, dct: dict, *, gh: Github = None, update: bool = False) -> T:
        """
        Create a GithubUser instance from a dictionary.
        Fetches user information from GitHub using the provided token.
        """
        username = dct.get('username')
        user = gh.get_user(username)
        return cls.create_from_obj(user, update=update)

    @classmethod
    def create_from_obj(cls, obj: github.NamedUser.NamedUser, **kwargs) -> 'GithubUser':
        return super().create_from_obj(obj, **kwargs)

    @classmethod
    def from_username(cls: T, username: str) -> T:
        """
        Fetch a GitHub user by username.
        Returns a GithubUser instance.
        """
        if username is None:
            return None
        user = GithubUser.objects.filter(username=username).first()
        if user is None:
            user = cls.create_from_dct({'username': username})
        return user

    def get_autocomplete_string(self):
        return self.username

    @classmethod
    def autocomplete_string_to_dct(cls, autocomplete_string: str) -> dict:
        """
        Convert an autocomplete string to a dictionary for GitHub user lookup.
        The string should be the GitHub username.
        """
        return {'username': autocomplete_string}

    @classmethod
    def filter_autocomplete_string(cls, autocomplete_string):
        return models.Q(username__istartswith=autocomplete_string)


    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.NamedUser.NamedUser:
        """
        Fetch the GitHub user object using the provided GitHub instance.
        This method is used to ensure that the GitHub user object is always up-to-date.
        """
        return gh.get_user_by_id(self.gh_id)

class GithubRepository(GithubMixin[github.Repository.Repository]):
    """Model representing a GitHub repository."""
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(GithubUser, related_name='repositories', on_delete=models.CASCADE)
    description = models.TextField(blank=True, null=True)

    obj_col_map = [
        ColObjMap('name', 'name'),
        ColObjMap('owner', 'owner.login', converter=GithubUser.from_username),
        ColObjMap('description', 'description', ''),
        ColObjMap('url', 'html_url'),
    ]

    def __str__(self):
        return f"{self.owner.username}/{self.name}"

    @classmethod
    @with_github
    def create_from_dct(cls: T, dct: dict, *, gh: Github, update: bool = False) -> T:
        """
        Create a GithubRepository instance from a dictionary.
        Fetches repository information from GitHub using the provided token.
        """
        name = dct.get('name')
        owner = dct.get('owner__username')
        repo = gh.get_repo(f"{owner}/{name}")
        return cls.create_from_obj(repo, update=update)

    def get_autocomplete_string(self):
        """
        Return a string representation for autocomplete purposes.
        This should be overridden in subclasses to provide meaningful information.
        """
        return f"{self.owner.username}/{self.name}"

    @classmethod
    def autocomplete_string_to_dct(cls, autocomplete_string: str) -> dict:
        """
        Convert an autocomplete string to a dictionary for GitHub repository lookup.
        The string should be in the format "owner/repo".
        """
        owner, name = autocomplete_string.split('/')

        return {'owner__username': owner, 'name': name}

    @classmethod
    def filter_autocomplete_string(cls, autocomplete_string: str):
        """
        Filter repositories based on an autocomplete string.
        This method should be overridden in subclasses to handle specific filtering logic.
        """
        owner, name = (autocomplete_string.split('/') + [''])[:2]
        res = models.Q(owner__username__istartswith=owner)
        if name:
            res &= models.Q(name__istartswith=name)
        return res

    @classmethod
    def from_user(cls: T, user: GithubUser) -> list[T]:
        """
        Fetch all repositories for a given GitHub user.
        Returns a list of GithubRepository instances.
        """
        repos = user.gh_obj.get_repos()
        return [cls.create_from_obj(repo) for repo in repos]

    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.Repository.Repository:
        """
        Fetch the GitHub repository object using the provided GitHub instance.
        This method is used to ensure that the GitHub repository object is always up-to-date.
        """
        return gh.get_repo(f"{self.owner.username}/{self.name}")

# class GithubBranch(GithubMixin):
#     """Model representing a GitHub branch."""
#     name = models.CharField(max_length=255)
#     repository = models.ForeignKey('GithubRepository', related_name='branches', on_delete=models.CASCADE)

#     id_key = ''
#     obj_col_map = [
#         ColObjMap('name', 'name'),
#         ColObjMap('url', 'commit.html_url'),
#     ]

#     @classmethod
#     def create_from_obj(cls, branch: github.Branch.Branch, repository: GithubRepository, **kwargs) -> 'GithubBranch':
#         """
#         Create a GithubBranch instance from a GitHub branch object.
#         This method is used to create an instance directly from the GitHub API object.
#         """
#         new = super().create_from_obj(branch, **kwargs)
#         new.repository = repository
#         new.save()
#         return new

#     @classmethod
#     def from_repository(cls: T, repository: GithubRepository) -> list[T]:
#         """
#         Fetch all branches for a given GitHub repository.
#         Returns a list of GithubBranch instances.
#         """
#         branches = repository.gh_obj.get_branches()
#         return [cls.create_from_obj(branch, repository) for branch in branches]

#     @property
#     def gh_obj(self) -> github.Branch.Branch:
#         return super().gh_obj

class GithubLabel(GithubMixin[github.Label.Label]):
    """Model representing a GitHub label."""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    repository = models.ForeignKey(GithubRepository, related_name='labels', on_delete=models.CASCADE)

    obj_col_map = [
        ColObjMap('name', 'name'),
        ColObjMap('description', 'description', ''),
        ColObjMap('url', 'url'),
    ]

    def __str__(self):
        return f"{self.repository.name}#{self.name}"

class GithubMilestone(GithubMixin[github.Milestone.Milestone]):
    """Model representing a GitHub milestone."""
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    state = models.CharField(max_length=50, choices=[('open', 'Open'), ('closed', 'Closed')], default='open')
    url = models.URLField(max_length=255, blank=True, null=True)

    created_by = models.ForeignKey(
        GithubUser, related_name='created_milestones', on_delete=models.CASCADE, null=True, blank=True
        )
    due_on = models.DateTimeField(null=True, blank=True)

    repository = models.ForeignKey(GithubRepository, related_name='milestones', on_delete=models.CASCADE)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    obj_col_map = [
        ColObjMap('url', 'html_url'),
        ColObjMap('title', 'title'),
        ColObjMap('description', 'description', ''),
        ColObjMap('state', 'state'),
        ColObjMap('created_by', 'creator.login', converter=GithubUser.from_username),
        ColObjMap('due_on', 'due_on', None),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('closed_at', 'closed_at', None)
    ]

    def __str__(self):
        return f"{self.repository.name}#{self.title} ({self.state})"

class GithubIssue(GithubMixin[github.Issue.Issue]):
    """Model representing a GitHub issue."""
    class Meta:
        unique_together = ('repository', 'number')
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    repository = models.ForeignKey(GithubRepository, related_name='issues', on_delete=models.CASCADE)
    number = models.PositiveIntegerField(
        unique=False, null=True, blank=True, help_text='Issue number in the repository'
    )

    is_closed = models.BooleanField(default=False)
    is_pr = models.BooleanField(default=False, help_text='Indicates if the issue is a pull request')

    created_by = models.ForeignKey(
        GithubUser, related_name='created_issues', on_delete=models.CASCADE, null=True, blank=True
        )
    closed_by = models.ForeignKey(
        GithubUser, related_name='closed_issues', on_delete=models.CASCADE, null=True, blank=True
        )

    assignees = models.ManyToManyField(GithubUser, related_name='assigned_issues', blank=True)
    labels = models.ManyToManyField('GithubLabel', related_name='issues', blank=True)
    milestone = models.ForeignKey(
        'GithubMilestone', related_name='issues', on_delete=models.CASCADE, null=True, blank=True
    )
    participants = models.ManyToManyField(GithubUser, related_name='participated_issues', blank=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    obj_col_map = [
        ColObjMap('url', 'html_url'),
        ColObjMap('title', 'title'),
        ColObjMap('body', 'body', ''),
        ColObjMap('number', 'number'),
        ColObjMap('is_closed', 'state', converter=lambda x: x == 'closed'),
        ColObjMap('is_pr', 'pull_request', converter=lambda x: x is not None),
        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('closed_by', 'closed_by.login', None, converter=GithubUser.from_username),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('closed_at', 'closed_at', None)
    ]

    def __str__(self):
        typ = 'PR' if self.is_pr else 'IS'
        return f"[{typ}] {self.repository.name} #{self.number:>6d}: {self.title}"

    def get_autocomplete_string(self):
        """
        Return a string representation for autocomplete purposes.
        This should be overridden in subclasses to provide meaningful information.
        """
        repo = self.repository
        owner = repo.owner.username
        return f"{owner}/{repo.name}#{self.number}: {self.title[:30]}"

    @classmethod
    def autocomplete_string_to_dct(cls, autocomplete_string: str) -> dict:
        """
        Convert an autocomplete string to a dictionary for GitHub issue lookup.
        The string should be in the format "repository#number: title".
        """
        data, _ = (autocomplete_string.split(':', 1) + [''])[:2]
        data, number = (data.split('#', 1) + [''])[:2]
        owner, repo_name = (data.split('/', 1) + [''])[:2]

        return {
            'repository__owner__username': owner,
            'repository__name': repo_name,
            'number': int(number)
        }

    @classmethod
    def filter_autocomplete_string(cls, autocomplete_string: str):
        """
        Filter issues based on an autocomplete string.
        The string should be in the format "repository#number: title".
        """
        data, _ = (autocomplete_string.split(':', 1) + [''])[:2]
        data, number = (data.split('#', 1) + [''])[:2]
        owner, repo_name = (data.split('/', 1) + [''])[:2]

        res = models.Q(repository__owner__username__istartswith=owner)
        if repo_name:
            res &= models.Q(repository__name__istartswith=repo_name)
        if number:
            res &= models.Q(number__startswith=number)
        return res

    @classmethod
    def from_repository(
            cls: T, repository: GithubRepository,
            do_prs: bool = False,
            update: bool = False,
            since: datetime = None
        ) -> list[T]:
        """
        Fetch all issues for a given GitHub repository.
        Returns a list of GithubIssue instances.
        """
        filter_args = {
            'state': 'all',
            'sort': 'created',
            'direction': 'asc'
        }
        if update:
            pass
        else:
            if since is None:
                last_created = cls.objects.filter(repository=repository).order_by('-created_at').first()
                if last_created:
                    since = last_created.created_at + timedelta(seconds=1)
                logger.info(f"Fetching from last created issue: {last_created},  since: {since}")
        if since:
            filter_args['since'] = since

        issues = repository.gh_obj.get_issues(**filter_args)
        issues.__class__.__len__ = lambda _: _.totalCount  # Override len to return total count
        issues = progress_bar(
            issues, description=f"Fetching issues from {repository}"
        )
        res = []
        for issue in issues:
            issue_obj = cls.create_from_obj(issue, foreign={'repository': repository}, update=update)
            res.append(issue_obj)
            if do_prs and issue.pull_request:
                GithubPullRequest.from_number(repository=repository, number=issue.number, update=update)
        return res

    def update(self):
        """
        Update the pull request object from GitHub.
        This method fetches the latest data from GitHub and updates the instance.
        """
        self.create_from_obj(self.gh_obj, foreign={'repository': self.repository}, update=True)

    def get_comments(self) -> list['GithubIssueComment']:
        """
        Fetch all comments for this pull request.
        Returns a list of GithubPRComment instances.
        """
        comments = self.gh_obj.get_comments()
        comments.__class__.__len__ = lambda _: _.totalCount  # Override len to return total count
        comments = progress_bar(
            comments, description=f"Fetching comments for {self}"
        )

        res = []
        for comment in comments:
            comment_obj = GithubIssueComment.create_from_obj(comment, foreign={'issue': self})
            res.append(comment_obj)

        return res

    def get_assignes(self) -> list[GithubUser]:
        """"Fetch the assignees data for the issue."""
        users = [GithubUser.from_username(assigne.login) for assigne in self.gh_obj.assignees]
        self.assignees.clear()  # Clear existing assignees
        self.assignees.add(*users)

        return users

    def get_participants(self) -> list[GithubUser]:
        """Fetch the participants data for the issue."""
        raise NotImplementedError('Need to implement participation from both commenters and other')

    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.Issue.Issue:
        """
        Fetch the GitHub issue object using the provided GitHub instance.
        This method is used to ensure that the GitHub issue object is always up-to-date.
        """
        return self.repository.gh_obj.get_issue(self.number)

class GithubIssueComment(GithubMixin[github.IssueComment.IssueComment]):
    """Model representing a GitHub comment."""
    body = models.TextField()
    issue = models.ForeignKey('GithubIssue', related_name='comments', on_delete=models.CASCADE)

    created_by = models.ForeignKey(
        GithubUser, related_name='created_comments', on_delete=models.CASCADE, null=True, blank=True
    )

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    obj_col_map = [
        ColObjMap('body', 'body'),
        ColObjMap('url', 'html_url'),
        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at', NODEFAULT)
    ]

class GithubPullRequest(GithubMixin[github.PullRequest.PullRequest]):
    """Model representing a GitHub Pull Request."""
    class Meta:
        unique_together = ('repository', 'number')
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    repository = models.ForeignKey(GithubRepository, related_name='pull_requests', on_delete=models.CASCADE)
    number = models.PositiveIntegerField(
        unique=False, null=True, blank=True, help_text='Pull request number in the repository'
    )

    is_draft = models.BooleanField(default=False)
    is_merged = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        GithubUser, related_name='created_pull_requests', on_delete=models.CASCADE, null=True, blank=True
        )
    merged_by = models.ForeignKey(
        GithubUser, related_name='merged_pull_requests', on_delete=models.CASCADE, null=True, blank=True
        )

    assignees = models.ManyToManyField(GithubUser, related_name='assigned_pull_requests', blank=True)
    reviewers = models.ManyToManyField(GithubUser, related_name='reviewed_pull_requests', blank=True)
    participants = models.ManyToManyField(GithubUser, related_name='participated_pull_requests', blank=True)

    labels = models.ManyToManyField('GithubLabel', related_name='pull_requests', blank=True)
    milestone = models.ForeignKey(
        'GithubMilestone', related_name='pull_requests', on_delete=models.CASCADE, null=True, blank=True
    )

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    merged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    obj_col_map= [
        ColObjMap('url', 'html_url'),
        ColObjMap('title', 'title'),
        ColObjMap('body', 'body', ''),
        ColObjMap('number', 'number'),

        ColObjMap('is_draft', 'draft', False),  # Default false needed to create PR from Issue
        ColObjMap('is_merged', 'merged', False),
        ColObjMap('is_closed', 'state', converter=lambda x: x == 'closed'),

        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('merged_by', 'merged_by.login', None, converter=GithubUser.from_username),

        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('merged_at', 'merged_at', None),
        ColObjMap('closed_at', 'closed_at', None)
    ]

    def __str__(self):
        repo = self.repository
        owner = repo.owner.username if repo.owner else 'unknown'
        return f"{owner}{repo.name}#{self.number}: {self.title} ({'Draft' if self.is_draft else 'PR'})"

    @classmethod
    def autocomplete_string_to_dct(cls, autocomplete_string: str) -> dict:
        """
        Convert an autocomplete string to a dictionary for GitHub issue lookup.
        The string should be in the format "repository#number: title".
        """
        data, _ = (autocomplete_string.split(':', 1) + [''])[:2]
        data, number = (data.split('#', 1) + [''])[:2]
        owner, repo_name = (data.split('/', 1) + [''])[:2]

        return {
            'repository__owner__username': owner,
            'repository__name': repo_name,
            'number': int(number)
        }

    def get_autocomplete_string(self):
        """
        Return a string representation for autocomplete purposes.
        This should be overridden in subclasses to provide meaningful information.
        """
        repo = self.repository
        owner = repo.owner.username
        return f"{owner}/{repo.name}#{self.number}"

    @classmethod
    def filter_autocomplete_string(cls, autocomplete_string: str):
        """
        Filter issues based on an autocomplete string.
        The string should be in the format "repository#number: title".
        """
        data, _ = (autocomplete_string.split(':', 1) + [''])[:2]
        data, number = (data.split('#', 1) + [''])[:2]
        owner, repo_name = (data.split('/', 1) + [''])[:2]

        res = models.Q(repository__owner__username__istartswith=owner)
        if repo_name:
            res &= models.Q(repository__name__istartswith=repo_name)
        if number:
            res &= models.Q(number__startswith=number)
        return res

    @classmethod
    def from_repository(cls, repository: GithubRepository) -> list['GithubPullRequest']:
        """
        Fetch all pull requests for a given GitHub repository.
        Returns a list of GithubPullRequest instances.
        """
        pull_requests = repository.gh_obj.get_pulls(state='all', sort='created', direction='desc')
        pull_requests.__class__.__len__ = lambda _: _.totalCount  # Override len to return total count
        pull_requests = progress_bar(
            pull_requests, total=pull_requests.totalCount, description=f'Fetching pull requests from {repository}'
        )

        # last_created_at = cls.objects.order_by('-created_at').first()
        # if last_created_at is None:

        res = []
        for pr in pull_requests:
            pr_obj = cls.create_from_obj(pr, foreign={'repository': repository})
            res.append(pr_obj)

        return res

    @classmethod
    def from_number(cls, repository: GithubRepository, number: int, update: bool = False) -> 'GithubPullRequest':
        """
        Fetch a pull request by its number from the given repository.
        Returns a GithubPullRequest instance.
        """
        pr = repository.gh_obj.get_pull(number)
        return cls.create_from_obj(pr, foreign={'repository': repository}, update=update)

    def update(self):
        """
        Update the pull request object from GitHub.
        This method fetches the latest data from GitHub and updates the instance.
        """
        self.create_from_obj(self.gh_obj, foreign={'repository': self.repository}, update=True)

    def get_comments(self) -> list['GithubPRComment']:
        """
        Fetch all comments for this pull request.
        Returns a list of GithubPRComment instances.
        """
        comments = self.gh_obj.get_comments()
        comments.__class__.__len__ = lambda _: _.totalCount  # Override len to return total count
        comments = progress_bar(
            comments, description=f"Fetching comments for {self}"
        )

        res = []
        for comment in comments:
            comment_obj = GithubPRComment.create_from_obj(comment, foreign={'pull_request': self})
            res.append(comment_obj)

        return res

    def get_assignes(self) -> list[GithubUser]:
        """"Fetch the assignees data for the issue."""
        users = [GithubUser.from_username(assigne.login) for assigne in self.gh_obj.assignees]
        self.assignees.clear()  # Clear existing assignees
        self.assignees.add(*users)

        return users

    def get_reviews(self) -> list['GithubPRReview']:
        """Fetch the reviewes data for the pull request."""
        reviews = self.gh_obj.get_reviews()
        reviews.__class__.__len__ = lambda _: _.totalCount  # Override len to return total count
        reviews = progress_bar(
            reviews, description=f"Fetching reviews for {self}"
        )
        res = []
        reviewers = []
        for review in reviews:
            review_obj = GithubPRReview.create_from_obj(review, foreign={'pull_request': self})
            reviewers.append(review_obj.created_by)
            res.append(review_obj)
        self.reviewers.clear()  # Clear existing reviewers
        self.reviewers.add(*reviewers)

        return res

    def get_participants(self) -> list[GithubUser]:
        """Fetch the participants data for the issue."""
        raise NotImplementedError('Need to implement participation from both commenters and other')

    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.PullRequest.PullRequest:
        """
        Fetch the GitHub pull request object using the provided GitHub instance.
        This method is used to ensure that the GitHub pull request object is always up-to-date.
        """
        return self.repository.gh_obj.get_pull(self.number)

class GithubPRComment(GithubMixin[github.PullRequestComment.PullRequestComment]):
    """Model representing a comment on a GitHub Pull Request."""
    body = models.TextField()
    pull_request = models.ForeignKey(GithubPullRequest, related_name='comments', on_delete=models.CASCADE)

    created_by = models.ForeignKey(
        GithubUser, related_name='created_pull_request_comments', on_delete=models.CASCADE, null=True, blank=True
    )

    created_at = models.DateTimeField()
    # updated_at = models.DateTimeField()

    obj_col_map = [
        ColObjMap('body', 'body'),
        ColObjMap('url', 'html_url'),
        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('created_at', 'created_at'),
    ]

    def __str__(self):
        return f"{self.pull_request} : {self.body[:30]}"

    # @classmethod
    # def from_pull_request(cls, pull_request: GithubPullRequest) -> list['GithubPRComment']:
    #     """
    #     Fetch all comments for a given GitHub pull request.
    #     Returns a list of GithubPRComment instances.
    #     """
    #     comments = pull_request.gh_obj.get_issue_comments()
    #     return [cls.create_from_obj(comment, foreign={'pull_request': pull_request}) for comment in comments]

class GithubPRReview(GithubMixin[github.PullRequestReview.PullRequestReview]):
    """Model representing a review on a GitHub Pull Request."""
    body = models.TextField()
    pull_request = models.ForeignKey(GithubPullRequest, related_name='reviews', on_delete=models.CASCADE)

    created_by = models.ForeignKey(
        GithubUser, related_name='created_pull_request_reviews', on_delete=models.CASCADE, null=True, blank=True
    )

    state = models.CharField(max_length=50, choices=[
        ('APPROVED', 'Approved'),
        ('CHANGES_REQUESTED', 'Changes Requested'),
        ('COMMENTED', 'Commented'),
        ('DISMISSED', 'Dismissed')
    ], default='COMMENTED')

    submitted_at = models.DateTimeField()

    obj_col_map = [
        ColObjMap('body', 'body'),
        ColObjMap('url', 'html_url'),
        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('state', 'state'),
        ColObjMap('submitted_at', 'submitted_at'),
    ]

    def __str__(self):
        return f"{self.pull_request} : {self.body[:30]} ({self.state})"

    # @classmethod
    # def from_pull_request(cls, pull_request: GithubPullRequest) -> list['GithubPRReview']:
    #     """
    #     Fetch all reviews for a given GitHub pull request.
    #     Returns a list of GithubPRReview instances.
    #     """
    #     reviews = pull_request.gh_obj.get_reviews()
    #     return [cls.create_from_obj(review, foreign={'pull_request': pull_request}) for review in reviews]
