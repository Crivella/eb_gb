"""GitHub-related models for Django application."""
import logging
import os
from functools import wraps
from typing import Any, Callable, TypeVar

import github
import github.Branch
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

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', None)

T = TypeVar('T', bound='GithubMixin')

logger = logging.getLogger('gh_db')


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


def user_converter(username: str) -> 'GithubUser':
    """
    Convert a GitHub username to a GithubUser instance.
    If the user does not exist, it will create a new instance.
    """
    if username is None:
        return None
    return GithubUser.from_dct({'username': username}, allow_new=True)

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


class GithubMixin(models.Model):
    """
    Mixin for common fields used in GitHub-related models.
    """
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
    def from_dct(cls: T, dct: dict, allow_new: bool = False, update: bool = False) -> T:
        """
        Create or update an instance from a dictionary.
        If the instance does not exist and allow_new is True, create a new instance.
        """
        instance = cls.objects.filter(**dct).first()
        if not instance and not allow_new:
            raise ValueError(f"{cls.__name__} with {dct} does not exist.")
        if not instance or update:
            instance = cls.create_from_dct(dct, update=update)
        return instance

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

        res, created = func(
            gh_id=gh_id,
            defaults=defaults
        )
        for key, val in foreign.items():
            setattr(res, key, val)
        if created:
            logger.debug(f"Created new {cls.__name__} instance: {res}")
        elif update:
            logger.debug(f"Updated existing {cls.__name__} instance: {res}")
        return res

    @property
    def gh_obj(self):
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

class GithubUser(GithubMixin):
    """Model representing a GitHub user."""
    username = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True, blank=True, null=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    # avatar_url = models.URLField(blank=True, null=True)

    obj_col_map = [
        ColObjMap('username', 'login'),
        ColObjMap('email', 'email', None),
        ColObjMap('url', 'html_url'),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
    ]

    @classmethod
    @with_github
    def create_from_dct(cls: T, dct: dict, *, gh: Github, update: bool = False) -> T:
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

    @property
    def gh_obj(self) -> github.NamedUser.NamedUser:
        return super().gh_obj


    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.NamedUser.NamedUser:
        """
        Fetch the GitHub user object using the provided GitHub instance.
        This method is used to ensure that the GitHub user object is always up-to-date.
        """
        return gh.get_user_by_id(self.gh_id)

    def __str__(self):
        return self.username

class GithubRepository(GithubMixin):
    """Model representing a GitHub repository."""
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(GithubUser, related_name='repositories', on_delete=models.CASCADE)
    description = models.TextField(blank=True, null=True)

    obj_col_map = [
        ColObjMap('name', 'name'),
        ColObjMap('owner', 'owner.login', converter=user_converter),
        ColObjMap('description', 'description', ''),
        ColObjMap('url', 'html_url'),
    ]

    @classmethod
    @with_github
    def create_from_dct(cls: T, dct: dict, *, gh: Github, update: bool = False) -> T:
        """
        Create a GithubRepository instance from a dictionary.
        Fetches repository information from GitHub using the provided token.
        """
        name = dct.get('name')
        owner = dct.get('owner', None)
        if owner is None:
            if '/' in name:
                if name.count('/') > 1:
                    raise ValueError(f"Invalid repository name: {name}")
                owner, name = name.split('/')
            else:
                raise ValueError(f"Owner must be specified for repository: {name}")
        repo = gh.get_repo(f"{owner}/{name}")
        return cls.create_from_obj(repo, update=update)

    @classmethod
    def create_from_obj(cls, obj: github.Repository.Repository, **kwargs) -> 'GithubRepository':
        return super().create_from_obj(obj, **kwargs)

    @classmethod
    def from_user(cls: T, user: GithubUser) -> list[T]:
        """
        Fetch all repositories for a given GitHub user.
        Returns a list of GithubRepository instances.
        """
        repos = user.gh_obj.get_repos()
        return [cls.create_from_obj(repo) for repo in repos]

    @property
    def gh_obj(self) -> github.Repository.Repository:
        return super().gh_obj

    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.Repository.Repository:
        """
        Fetch the GitHub repository object using the provided GitHub instance.
        This method is used to ensure that the GitHub repository object is always up-to-date.
        """
        return gh.get_repo(f"{self.owner.username}/{self.name}")

    def __str__(self):
        return f"{self.name} by @{self.owner.username}"

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

class GithubLabel(GithubMixin):
    """Model representing a GitHub label."""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    repository = models.ForeignKey(GithubRepository, related_name='labels', on_delete=models.CASCADE)

    obj_col_map = [
        ColObjMap('name', 'name'),
        ColObjMap('description', 'description', ''),
        ColObjMap('url', 'url'),
    ]

    @classmethod
    def create_from_obj(cls, obj: github.Label.Label, **kwargs) -> 'GithubLabel':
        """
        Create a GithubLabel instance from a GitHub label object.
        This method is used to create an instance directly from the GitHub API object.
        """
        return super().create_from_obj(obj, **kwargs)

    @property
    def gh_obj(self) -> github.Label.Label:
        return super().gh_obj

class GithubMilestone(GithubMixin):
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
        ColObjMap('created_by', 'creator.login', converter=user_converter),
        ColObjMap('due_on', 'due_on', None),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('closed_at', 'closed_at', None)
    ]

    @classmethod
    def create_from_obj(cls,obj: github.Milestone.Milestone, **kwargs) -> 'GithubMilestone':
        """
        Create a GithubMilestone instance from a GitHub milestone object.
        This method is used to create an instance directly from the GitHub API object.
        """
        return super().create_from_obj(obj, **kwargs)

    @property
    def gh_obj(self) -> github.Milestone.Milestone:
        return super().gh_obj

class GithubIssue(GithubMixin):
    """Model representing a GitHub issue."""
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    repository = models.ForeignKey(GithubRepository, related_name='issues', on_delete=models.CASCADE)
    number = models.PositiveIntegerField(
        unique=True, null=True, blank=True, help_text='Issue number in the repository'
    )

    is_closed = models.BooleanField(default=False)

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
        ColObjMap('created_by', 'user.login', converter=user_converter),
        ColObjMap('closed_by', 'closed_by.login', None, converter=user_converter),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('closed_at', 'closed_at', None)
    ]

    @classmethod
    def create_from_dct(cls: T, dct: dict, *, gh: Github = None, update: bool = False) -> T:
        """
        Create a GithubIssue instance from a dictionary.
        Fetches issue information from GitHub using the provided token.
        """
        gh_id = dct.get('id')
        repository: GithubRepository = dct.get('repository')
        if isinstance(gh_id, str):
            if not gh_id.isdigit():
                raise ValueError(f"Invalid issue ID: {gh_id}")
            gh_id = int(id)
        issue = repository.gh_obj.get_issue(gh_id)
        return cls.create_from_obj(issue, foreign={'repository':repository}, update=update)

    @classmethod
    def create_from_obj(cls, obj: github.Issue.Issue, **kwargs) -> 'GithubIssue':
        """
        Create a GithubIssue instance from a GitHub issue object.
        This method is used to create an instance directly from the GitHub API object.
        """
        new = super().create_from_obj(obj, **kwargs)
        for assignee in obj.assignees:
            new.assignees.add(GithubUser.from_dct({'username': assignee.login}, allow_new=True))
        # for participant in issue.participants:
        #     # Handle participants
        new.save()
        return new

    @classmethod
    def from_repository(cls: T, repository: GithubRepository) -> list[T]:
        """
        Fetch all issues for a given GitHub repository.
        Returns a list of GithubIssue instances.
        """
        issues = repository.gh_obj.get_issues(state='all')
        return [cls.create_from_obj(issue, foreign={'repository':repository}) for issue in issues]

    def get_comments(self) -> list['GithubIssueComment']:
        """
        Fetch all comments for this pull request.
        Returns a list of GithubPRComment instances.
        """
        return [
            GithubIssueComment.create_from_obj(comment, foreign={'issue':self})
            for comment in self.gh_obj.get_comments()
        ]

    @property
    def gh_obj(self) -> github.Issue.Issue:
        return super().gh_obj

    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.Issue.Issue:
        """
        Fetch the GitHub issue object using the provided GitHub instance.
        This method is used to ensure that the GitHub issue object is always up-to-date.
        """
        return self.repository.gh_obj.get_issue(self.number)

    def __str__(self):
        return f"Issue: {self.title} in {self.repository.name}"

class GithubIssueComment(GithubMixin):
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
        ColObjMap('created_by', 'user.login', converter=user_converter),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at', NODEFAULT)
    ]

    @classmethod
    def create_from_obj(cls,obj: github.IssueComment.IssueComment, **kwargs) -> 'GithubIssueComment':
        """
        Create a GithubComment instance from a GitHub issue comment object.
        This method is used to create an instance directly from the GitHub API object.
        """
        return super().create_from_obj(obj, **kwargs)

    @property
    def gh_obj(self) -> github.IssueComment.IssueComment:
        return super().gh_obj

class GithubPullRequest(GithubMixin):
    """Model representing a GitHub Pull Request."""
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    repository = models.ForeignKey(GithubRepository, related_name='pull_requests', on_delete=models.CASCADE)
    number = models.PositiveIntegerField(
        unique=True, null=True, blank=True, help_text='Pull request number in the repository'
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
    # closed_by = models.ForeignKey(
    #     GithubUser, related_name='closed_pull_requests', on_delete=models.CASCADE, null=True, blank=True
    # )

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

        ColObjMap('is_draft', 'draft'),
        ColObjMap('is_merged', 'merged'),
        ColObjMap('is_closed', 'state', converter=lambda x: x == 'closed'),

        ColObjMap('created_by', 'user.login', converter=user_converter),
        ColObjMap('merged_by', 'merged_by.login', converter=user_converter),

        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('merged_at', 'merged_at', None),
        ColObjMap('closed_at', 'closed_at', None)

    ]

    def __str__(self):
        return f"PR: {self.title} in {self.repository.name}"

    @classmethod
    def create_from_dct(cls: T, dct: dict, *, gh: Github = None, update: bool = False) -> T:
        """
        Create a GithubPullRequest instance from a dictionary.
        Fetches pull request information from GitHub using the provided token.
        """
        pr_id = dct.get('id')
        repository: GithubRepository = dct.get('repository')
        if isinstance(pr_id, str):
            if not pr_id.isdigit():
                raise ValueError(f"Invalid pull request ID: {pr_id}")
            pr_id = int(pr_id)
        pr = repository.gh_obj.get_pull(pr_id)
        return cls.create_from_obj(pr, foreign={'repository':repository}, update=update)

    @classmethod
    def create_from_obj(cls,obj: github.PullRequest.PullRequest, **kwargs) -> 'GithubPullRequest':
        """
        Create a GithubPullRequest instance from a GitHub pull request object.
        This method is used to create an instance directly from the GitHub API object.
        """
        new = super().create_from_obj(obj, **kwargs)
        for assignee in obj.assignees:
            new.assignees.add(GithubUser.from_dct({'username': assignee.login}, allow_new=True))
        for rev in obj.get_reviews():
            rev_obj = GithubPRReview.create_from_obj(rev, pull_request=new)
            new.reviewers.add(rev_obj.created_by)
        # for participant in pr.get_participants():
        #     # : Handle participants
        return new

    @classmethod
    def from_repository(cls: T, repository: GithubRepository) -> list[T]:
        """
        Fetch all pull requests for a given GitHub repository.
        Returns a list of GithubPullRequest instances.
        """
        pull_requests = repository.gh_obj.get_pulls(state='all')
        return [cls.create_from_obj(pr, foreign={'repository':repository}) for pr in pull_requests]

    @property
    def gh_obj(self) -> github.PullRequest.PullRequest:
        return super().gh_obj

    @with_github
    def get_gh_obj(self, *, gh: Github) -> github.PullRequest.PullRequest:
        """
        Fetch the GitHub pull request object using the provided GitHub instance.
        This method is used to ensure that the GitHub pull request object is always up-to-date.
        """
        repo = self.repository.gh_obj
        return repo.get_pull(self.pk)

class GithubPRComment(GithubMixin):
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
        ColObjMap('created_by', 'user.login', converter=user_converter),
        ColObjMap('created_at', 'created_at'),
    ]

    @classmethod
    def create_from_obj(cls,obj: github.PullRequestComment.PullRequestComment, **kwargs) -> 'GithubPRComment':
        """
        Create a GithubPRComment instance from a GitHub pull request comment object.
        This method is used to create an instance directly from the GitHub API object.
        """
        return super().create_from_obj(obj, **kwargs)

    @classmethod
    def from_pull_request(cls, pull_request: GithubPullRequest) -> list['GithubPRComment']:
        """
        Fetch all comments for a given GitHub pull request.
        Returns a list of GithubPRComment instances.
        """
        comments = pull_request.gh_obj.get_issue_comments()
        return [cls.create_from_obj(comment, foreign={'pull_request':pull_request}) for comment in comments]

    @property
    def gh_obj(self) -> github.PullRequestComment.PullRequestComment:
        return super().gh_obj

class GithubPRReview(GithubMixin):
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
        ColObjMap('created_by', 'user.login', converter=user_converter),
        ColObjMap('state', 'state'),
        ColObjMap('submitted_at', 'submitted_at'),
    ]

    @classmethod
    def create_from_obj(cls,obj: github.PullRequestReview.PullRequestReview, **kwargs) -> 'GithubPRReview':
        """
        Create a GithubPRReview instance from a GitHub pull request review object.
        This method is used to create an instance directly from the GitHub API object.
        """
        return super().create_from_obj(obj, **kwargs)

    @classmethod
    def from_pull_request(cls, pull_request: GithubPullRequest) -> list['GithubPRReview']:
        """
        Fetch all reviews for a given GitHub pull request.
        Returns a list of GithubPRReview instances.
        """
        reviews = pull_request.gh_obj.get_reviews()
        return [cls.create_from_obj(review, foreign={'pull_request':pull_request}) for review in reviews]
