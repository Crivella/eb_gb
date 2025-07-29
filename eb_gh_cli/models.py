"""GitHub-related models for Django application."""
# https://github.com/typeddjango/django-stubs/issues/299  for migrations with Generic
import logging
import os
import subprocess
import sys
from typing import Any, Callable, Generic, Self, TypeVar

import django
import django.db.utils
from django.core.files.base import ContentFile
from django.db import models

from . import gh_api
from .progress import progress_bar, progress_clean_tasks

O = TypeVar('O', bound=gh_api.GithubObject)

logger = logging.getLogger('gh_db')



try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eb_gh_cli.settings')
    django.setup()
except RuntimeError as e:
    pass

LIMIT_REJECTED_PRFILES = os.environ.get('LIMIT_REJECTED_PRFILES', 100)
try:
    LIMIT_REJECTED_PRFILES = int(LIMIT_REJECTED_PRFILES)
except ValueError:
    logger.error(
        f'LIMIT_REJECTED_PRFILES environment variable is not an integer: {LIMIT_REJECTED_PRFILES}. '
        'Defaulting to 100.'
    )
    LIMIT_REJECTED_PRFILES = 100

class NODEFAULT:
    """A sentinel value to indicate that a default value is not provided."""

class ColObjMap:
    """
    A class to represent a mapping between model fields and GitHub object attributes.
    This is used to define how to extract data from GitHub objects when creating or updating Django models.
    """
    def __init__(self, column: str, param: str, *, default: Any = NODEFAULT, converter: Callable = None):
        self.column = column
        self.param = param
        self.default = default
        self.converter = converter if converter else lambda x: x

    def __iter__(self):
        yield self.column
        yield self.param
        yield self.default
        yield self.converter


class GithubMixin(models.Model, Generic[O]):
    """Mixin for common fields used in GitHub-related models."""
    gh_id = models.BigIntegerField(unique=True, null=True, help_text='GitHub ID of the object')
    url = models.URLField(max_length=255, blank=True, null=True)

    internal_created_at = models.DateTimeField(auto_now_add=True)
    internal_updated_at = models.DateTimeField(auto_now=True)

    id_key: str = 'id'
    url_key: str = 'html_url'
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
            cls, autocomplete_string: str,
            allow_new: bool = False,
            update: bool = False
        ) -> Self:
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
    def filter_autocomplete_string(cls, autocomplete_string: str) -> models.Q:
        """
        Filter instances based on an autocomplete string.
        This method should be overridden in subclasses to handle specific filtering logic.
        """
        raise cls.DoesNotSupportDirectCreation(
            f"{cls.__class__.__name__}.filter_autocomplete_string must be implemented."
        )

    @classmethod
    def create_from_dct(cls, dct: dict, *, update: bool = False) -> Self:
        """
        Create a new instance from the provided keyword arguments.
        This method should be overridden in subclasses to handle specific creation logic.
        """
        raise cls.DoesNotSupportDirectCreation(f"{cls.__name__}.create_from_dct must be implemented.")

    @classmethod
    def create_from_obj(cls, obj, **kwargs) -> Self:
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

        create_keys = {}
        if cls.id_key:
            id_key = cls.id_key.split('.')
            gh_id = obj
            for key in id_key:
                gh_id = getattr(gh_id, key)
            create_keys['gh_id'] = gh_id

        if cls.url_key:
            url_key = cls.url_key.split('.')
            url = obj
            for key in url_key:
                url = getattr(url, key)
            create_keys['url'] = url

        for key, val in foreign.items():
            defaults[key] = val

        try:
            res, created = func(
                **create_keys,
                defaults=defaults
            )
        except OSError as e:
            logger.error(f"Error creating {cls.__name__} instance: {e}", exc_info=True)
            logger.error(f"`lsof -p {os.getpid()}` to check for open files.")
            data = subprocess.check_output(['lsof', '-p', str(os.getpid())])
            logger.error(f"Open files: \n{data.decode('utf-8')}")
            sys.exit(1)
        except django.db.utils.IntegrityError as e:
            logger.error(f"Integrity error while creating {cls.__name__} instance: {e}", exc_info=True)
            logger.error(f'Create keys: {create_keys}, defaults: {defaults}')
            sys.exit(1)
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

    def get_gh_obj(self) -> O:
        """
        Fetch the GitHub object associated with this instance.
        This method should be overridden in subclasses to fetch the appropriate GitHub object.
        """
        raise self.DoesNotSupportDirectCreation(f"{self.__class__.__name__}.get_gh_obj must be implemented.")

    def update_related(self, rel_name: str, objects: list):
        """
        Update a related field with a list of objects.
        This method is used to update many-to-many relationships.
        """
        rel = getattr(self, rel_name)
        prev = set(rel.all())
        new = set(objects)
        to_remove = prev - new
        to_add = new - prev
        if to_remove:
            rel.remove(*to_remove)
            logger.debug(f"Removed {len(to_remove)} objects from {rel_name} for {self}.")
        if to_add:
            rel.add(*to_add)
            logger.debug(f"Added {len(to_add)} objects to {rel_name} for {self}.")

class GithubUser(GithubMixin[gh_api.NamedUser]):
    """Model representing a GitHub user."""
    username = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=False, blank=True, null=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    obj_col_map = [
        ColObjMap('username', 'login'),
        ColObjMap('email', 'email', default=None),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
    ]

    def __str__(self):
        return self.username

    @classmethod
    def create_from_dct(cls, dct: dict, *, update: bool = False) -> Self:
        """
        Create a GithubUser instance from a dictionary.
        Fetches user information from GitHub using the provided token.
        """
        username = dct.get('username')
        if not update:
            user = cls.objects.filter(username=username).first()
            if user is not None:
                return user
        try:
            user = gh_api.get_gh_main().get_user(username)
        except gh_api.UnknownObjectException:
            mock_date = '2000-01-01T00:00:00Z'
            user, _ = cls.objects.get_or_create(
                username=username,
                defaults={'email': None, 'created_at': mock_date, 'updated_at': mock_date}
            )
            return user
        return cls.create_from_obj(user, update=update)

    @classmethod
    def from_username(cls, username: str) -> Self:
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
    def filter_autocomplete_string(cls, autocomplete_string) -> models.Q:
        return models.Q(username__istartswith=autocomplete_string)

    def get_gh_obj(self) -> gh_api.NamedUser:
        """
        Fetch the GitHub user object using the provided GitHub instance.
        This method is used to ensure that the GitHub user object is always up-to-date.
        """
        return gh_api.get_gh_main().get_user_by_id(self.gh_id)

class GithubRepository(GithubMixin[gh_api.Repository]):
    """Model representing a GitHub repository."""
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(GithubUser, related_name='repositories', on_delete=models.CASCADE)
    description = models.TextField(blank=True, null=True)

    obj_col_map = [
        ColObjMap('name', 'name'),
        ColObjMap('owner', 'owner.login', converter=GithubUser.from_username),
        ColObjMap('description', 'description', default=None),
    ]

    def __str__(self):
        return f"{self.owner.username}/{self.name}"

    @classmethod
    def create_from_dct(cls, dct: dict, *, update: bool = False) -> Self:
        """
        Create a GithubRepository instance from a dictionary.
        Fetches repository information from GitHub using the provided token.
        """
        name = dct.get('name')
        owner = dct.get('owner__username')
        if not update:
            repo = cls.objects.filter(name=name, owner__username=owner).first()
            if repo is not None:
                return repo
        repo = gh_api.get_gh_main().get_repo(f"{owner}/{name}")
        return cls.create_from_obj(repo, update=update)

    def get_autocomplete_string(self) -> str:
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
    def filter_autocomplete_string(cls, autocomplete_string: str) -> models.Q:
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
    def from_user(cls, user: GithubUser) -> list[Self]:
        """
        Fetch all repositories for a given GitHub user.
        Returns a list of GithubRepository instances.
        """
        repos = user.gh_obj.get_repos()
        return [cls.create_from_obj(repo) for repo in repos]

    def get_gh_obj(self) -> gh_api.Repository:
        """
        Fetch the GitHub repository object using the provided GitHub instance.
        This method is used to ensure that the GitHub repository object is always up-to-date.
        """
        return gh_api.get_gh_main().get_repo(f"{self.owner.username}/{self.name}")

# class GithubBranch(GithubMixin):
#     """Model representing a GitHub branch."""
#     name = models.CharField(max_length=255)
#     repository = models.ForeignKey('GithubRepository', related_name='branches', on_delete=models.CASCADE)

#     id_key = ''
#     obj_col_map = [
#         ColObjMap('name', 'name'),
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
#     def from_repository(cls, repository: GithubRepository) -> list[Self]:
#         """
#         Fetch all branches for a given GitHub repository.
#         Returns a list of GithubBranch instances.
#         """
#         branches = repository.gh_obj.get_branches()
#         return [cls.create_from_obj(branch, repository) for branch in branches]

#     @property
#     def gh_obj(self) -> github.Branch.Branch:
#         return super().gh_obj

class GithubLabel(GithubMixin[gh_api.Label]):
    """Model representing a GitHub label."""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    repository = models.ForeignKey(GithubRepository, related_name='labels', on_delete=models.CASCADE)

    url_key = 'url'

    obj_col_map = [
        ColObjMap('name', 'name'),
        ColObjMap('description', 'description', default=None),
    ]

    def __str__(self):
        return f"{self.repository.name}#{self.name}"

class GithubMilestone(GithubMixin[gh_api.Milestone]):
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
        ColObjMap('title', 'title'),
        ColObjMap('description', 'description', default=None),
        ColObjMap('state', 'state'),
        ColObjMap('created_by', 'creator.login', converter=GithubUser.from_username),
        ColObjMap('due_on', 'due_on', default=None),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('closed_at', 'closed_at', default=None)
    ]

    def __str__(self):
        return f"{self.repository.name}#{self.title} ({self.state})"

class GithubIssue(GithubMixin[gh_api.Issue]):
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
        ColObjMap('title', 'title'),
        ColObjMap('body', 'body', default=None),
        ColObjMap('number', 'number'),
        ColObjMap('is_closed', 'state', converter=lambda x: x == 'closed'),
        ColObjMap('is_pr', 'pull_request', converter=lambda x: x is not None),
        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('closed_by', 'closed_by.login', default=None, converter=GithubUser.from_username),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('closed_at', 'closed_at', default=None)
    ]

    def __str__(self):
        typ = 'PR' if self.is_pr else 'IS'
        return f"[{typ}] {self.repository.name} #{self.number:>6d}: {self.title}"

    def get_autocomplete_string(self) -> str:
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
    def filter_autocomplete_string(cls, autocomplete_string: str) -> models.Q:
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
            cls, repository: GithubRepository,
            do_prs: bool = False,
            do_comments: bool = False,
            do_files: bool = False,
            do_commits: bool = False,
            update: bool = False,
            # since: datetime = None,
            since_number: int = None
        ) -> list[Self]:
        """
        Fetch all issues for a given GitHub repository.
        Returns a list of GithubIssue instances.
        """
        filter_args = {
            'state': 'all',
            'sort': 'created',
            'direction': 'desc'
        }
        if not update:
            if since_number is None:
                last_created = cls.objects.filter(repository=repository).order_by('-created_at').first()
                if last_created:
                    since_number = last_created.number + 1
        if since_number is None:
            since_number = 1

        res = []
        repo = repository.gh_obj

        last_issue_num = repo.get_issues(**filter_args)[0].number

        iterator = progress_bar(
            range(since_number, last_issue_num + 1),
            description=f"Fetching issues from {repository} since #{since_number}",
        )
        for issue_number in iterator:
            try:
                issue = repo.get_issue(number=issue_number)
            except gh_api.UnknownObjectException:
                logger.warning(f"Issue #{issue_number} not found in {repository}. Skipping.")
                continue
            except Exception as e:
                logger.error(f"Error fetching issue #{issue_number}: {e}", exc_info=True)
                continue
            try:
                remote_repo_name = issue.repository.name
                remote_repo_inum = issue.number
            except Exception as e:
                logger.error(f"Error accessing issue repository or number: {e}", exc_info=True)
                continue
            if repo.name != remote_repo_name or issue_number != remote_repo_inum:
                logger.info(
                    f'Issue mismatch: requested = {repo.owner.login}/{repo.name}#{issue_number}, '
                    f'got = {issue.repository.owner.login}/{issue.repository.name}#{issue.number}\n'
                    'Probably due to a redirect/transfered issue... Skipping.'
                )
                continue
            try:
                issue_obj = cls.create_from_obj(issue, foreign={'repository': repository}, update=update)
                issue_obj.get_assignes()

                if do_comments:
                    issue_obj.get_comments()
            except Exception as e:
                logger.error(f"Error processing issue #{issue_number}: {e}", exc_info=True)
                sys.exit(1)

            res.append(issue_obj)
            if do_prs and issue.pull_request:
                try:
                    pr_obj = GithubPullRequest.from_number(
                        repository=repository, number=issue_number, update=update
                    )
                    pr_obj.get_assignes()
                    if do_comments:
                        pr_obj.get_reviews()
                    if do_files:
                        pr_obj.get_files()
                    if do_commits:
                        pr_obj.get_commits(do_files=do_files)
                except Exception as e:
                    logger.error(f"Error processing PR for issue #{issue_number}: {e}", exc_info=True)
                    sys.exit(1)
            progress_clean_tasks()
        return res

    def update(self) -> Self | None:
        """
        Update the issue object from GitHub.
        This method fetches the latest data from GitHub and updates the instance.
        """
        if self.gh_obj.updated_at > self.updated_at:
            # Fetch the latest issue object from GitHub
            pre_num_comments = self.comments.count()
            pre_num_assignes = self.assignees.count()

            new = self.create_from_obj(self.gh_obj, foreign={'repository': self.repository}, update=True)
            new.get_assignes()  # Fetch assignees after updating the issue
            new.get_comments()  # Fetch comments after updating the issue

            post_num_comments = new.comments.count()
            post_num_assignes = new.assignees.count()

            msg = []
            if pre_num_comments != post_num_comments:
                msg.append(f"Comments: {pre_num_comments} -> {post_num_comments}")
            if pre_num_assignes != post_num_assignes:
                msg.append(f"Assignees: {pre_num_assignes} -> {post_num_assignes}")

            if new.is_closed:
                msg.append(f"Closed at: {new.closed_at}")

            if not msg:
                msg.append('No changes detected.')

            logger.info(f"Updated Issue #{new.number}: {', '.join(msg)}")

            return new
        return None

    def get_comments(self) -> list['GithubIssueComment']:
        """
        Fetch all comments for this issue.
        Returns a list of GithubIssueComment instances.
        """
        comments = self.gh_obj.get_comments()
        comments = progress_bar(
            comments, total=comments.totalCount, description=f"-- Fetching comments for Issue#{self.number}"
        )

        res = []
        for comment in comments:
            comment_obj = GithubIssueComment.create_from_obj(comment, foreign={'issue': self})
            res.append(comment_obj)

        return res

    def get_assignes(self) -> list[GithubUser]:
        """"Fetch the assignees data for the issue."""
        users = [GithubUser.from_username(assigne.login) for assigne in self.gh_obj.assignees]

        self.update_related('assignees', users)
        return users

    def get_participants(self) -> list[GithubUser]:
        """Fetch the participants data for the issue."""
        raise NotImplementedError('Need to implement participation from both commenters and other')

    def get_gh_obj(self) -> gh_api.Issue:
        """
        Fetch the GitHub issue object using the provided GitHub instance.
        This method is used to ensure that the GitHub issue object is always up-to-date.
        """
        return self.repository.gh_obj.get_issue(self.number)

class GithubIssueComment(GithubMixin[gh_api.IssueComment]):
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
        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at')
    ]

class GithubCommit(GithubMixin[gh_api.Commit]):
    """Model representing a GitHub commit."""
    class Meta:
        unique_together = ('repository', 'sha')
    sha = models.CharField(max_length=40, unique=True)
    message = models.TextField(blank=True, null=True)
    author = models.ForeignKey(
        GithubUser, related_name='authored_commits', on_delete=models.CASCADE, null=True, blank=True
    )
    # This seems equivalent to the author by looking at the REST API documentation
    # committer = models.ForeignKey(
    #     GithubUser, related_name='committed_commits', on_delete=models.CASCADE, null=True, blank=True
    # )

    repository = models.ForeignKey(GithubRepository, related_name='commits', on_delete=models.CASCADE)

    parents = models.ManyToManyField(
        'self', symmetrical=False, related_name='child_commits', blank=True,
        help_text='Parent commits of this commit'
    )

    last_modified = models.DateTimeField(help_text='Last modified time of the commit')

    id_key = None
    url_key = 'url'

    obj_col_map = [
        ColObjMap('sha', 'sha'),
        ColObjMap('message', 'commit.message', default=None),
        ColObjMap('author', 'author.login', default=None, converter=GithubUser.from_username),
        # ColObjMap('committer', 'committer.login', default=None, converter=GithubUser.from_username),
        ColObjMap('last_modified', 'last_modified_datetime')
    ]

    def __str__(self):
        return f"{self.repository.name}#{self.sha[:7]}: {self.message[:30]}"

    def get_files(self, pull_request: 'GithubPullRequest' = None) -> list['GithubFile']:
        """
        Fetch all files associated with this commit.
        Returns a list of GithubFile instances.
        """
        files = self.gh_obj.files
        total = files.totalCount
        if pull_request is not None:
            if total > LIMIT_REJECTED_PRFILES and pull_request.is_closed and not pull_request.is_merged:
                logger.warning(
                    f"Commit {self.sha[:8]} has {total} files changed, "
                    'and is closed but not merged. Skipping files...'
                )
                return []
        if total > 3000:
            logger.warning(
                f"Commit #{self.sha[:8]} has {total} files (>3000 limit for REST API). Limiting to 3000 files.."
            )
            total = 3000
        files = progress_bar(
            files, total=total,
            description=f"-- Fetching files for Commit {self.sha[:8]} in {self.repository.name}"
        )

        res = []
        for file in files:
            file_obj = GithubFile.create_from_obj(file, foreign={'commit': self})
            res.append(file_obj)

        return res

    def get_parents(self) -> list['GithubCommit']:
        """
        Fetch the parent commits of this commit.
        Returns a list of GithubCommit instances.
        """
        parents = self.gh_obj.parents
        parents = progress_bar(
            parents, total=len(parents),
            description=f"-- Fetching parents for Commit {self.sha[:8]} in {self.repository.name}"
        )

        res = []
        for parent in parents:
            parent_obj = GithubCommit.create_from_obj(parent, foreign={'repository': self.repository})
            res.append(parent_obj)

        self.update_related('parents', res)
        return res

    def get_gh_obj(self) -> gh_api.Commit:
        """
        Fetch the GitHub commit object using the provided GitHub instance.
        This method is used to ensure that the GitHub commit object is always up-to-date.
        """
        return self.repository.gh_obj.get_commit(self.sha)

class GithubPullRequest(GithubMixin[gh_api.PullRequest]):
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

    commits = models.ManyToManyField(
        GithubCommit, related_name='pull_requests', blank=True,
        help_text='Commits associated with this pull request'
    )

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    merged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    obj_col_map= [
        ColObjMap('title', 'title'),
        ColObjMap('body', 'body', default=None),
        ColObjMap('number', 'number'),

        ColObjMap('is_draft', 'draft', default=False),  # Default false needed to create PR from Issue
        ColObjMap('is_merged', 'merged', default=False),
        ColObjMap('is_closed', 'state', converter=lambda x: x == 'closed'),

        ColObjMap('created_by', 'user.login', converter=GithubUser.from_username),
        ColObjMap('merged_by', 'merged_by.login', default=None, converter=GithubUser.from_username),

        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
        ColObjMap('merged_at', 'merged_at', default=None),
        ColObjMap('closed_at', 'closed_at', default=None)
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

    def get_autocomplete_string(self) -> str:
        """
        Return a string representation for autocomplete purposes.
        This should be overridden in subclasses to provide meaningful information.
        """
        repo = self.repository
        owner = repo.owner.username
        return f"{owner}/{repo.name}#{self.number}"

    @classmethod
    def filter_autocomplete_string(cls, autocomplete_string: str) -> models.Q:
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
        pull_requests = progress_bar(
            pull_requests, total=pull_requests.totalCount,
            description=f'Fetching pull requests from {repository}'
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

    def update(self) -> Self | None:
        """
        Update the pull request object from GitHub.
        This method fetches the latest data from GitHub and updates the instance.
        """
        if self.gh_obj.updated_at > self.updated_at:
            prev_num_files = self.files.count()
            prev_num_assignees = self.assignees.count()
            prev_num_reviews = self.reviews.count()

            new = self.create_from_obj(self.gh_obj, foreign={'repository': self.repository}, update=True)
            new.get_assignes()
            new.get_reviews()  # Fetch reviews after updating the PR
            new.get_files()  # Fetch files after updating the PR

            post_num_files = new.files.count()
            post_num_assignees = new.assignees.count()
            post_num_reviews = new.reviews.count()

            msg = []
            if post_num_files != prev_num_files:
                msg.append(f"#Files: {prev_num_files} -> {post_num_files}")
            if post_num_assignees != prev_num_assignees:
                msg.append(f"#Assignees: {prev_num_assignees} -> {post_num_assignees}")
            if post_num_reviews != prev_num_reviews:
                msg.append(f"#Reviews: {prev_num_reviews} -> {post_num_reviews}")

            if new.is_closed:
                if new.is_merged:
                    msg.append(f'PR merged at: {new.merged_at}')
                else:
                    msg.append(f'PR closed at: {new.closed_at}')

            if not msg:
                msg.append('No changes detected')

            logger.info(f"Updated PR {new.number}:  {', '.join(msg)}")

            return new
        return None

    def get_assignes(self) -> list[GithubUser]:
        """"Fetch the assignees data for the issue."""
        users = [GithubUser.from_username(assigne.login) for assigne in self.gh_obj.assignees]

        self.update_related('assignees', users)
        return users

    def get_reviews(self) -> list['GithubPRReview']:
        """Fetch the reviewes data for the pull request."""
        reviews = self.gh_obj.get_reviews()
        reviews = progress_bar(
            reviews, total=reviews.totalCount,
            description=f"-- Fetching reviews for PR#{self.number}"
        )
        res = []
        reviewers = []
        for review in reviews:
            review_obj = GithubPRReview.create_from_obj(review, foreign={'pull_request': self})
            reviewers.append(review_obj.created_by)
            res.append(review_obj)

        self.update_related('reviews', res)
        return res

    def get_files(self) -> list['GithubFile']:
        """Fetch the files changed in the pull request."""
        try:
            files = self.gh_obj.get_files()
            total = files.totalCount
        except gh_api.GithubException as e:
            logger.warning(f'Error fetching files for {self}: {e}')
            return []
        if total > LIMIT_REJECTED_PRFILES and self.is_closed and not self.is_merged:
            logger.warning(
                f"Pull request {self.number} has {total} files changed, "
                'and is closed but not merged. Skipping files...'
            )
            return []
        if total >= 3000:
            logger.warning(
                f"Pull request #{self.number} has {total} files (>3000 limit for REST API). Limiting to 3000 files.."
            )
            total = 3000
        files = progress_bar(
            files, total=total,
            description=f"-- Fetching files for PR#{self.number}"
        )
        res = []
        try:
            for file in files:
                file_obj = GithubFile.create_from_obj(file, foreign={'pull_request': self})
                res.append(file_obj)
        except gh_api.GithubException as e:
            logger.warning(f'Error fetching files for {self}: {e}')
        return res

    def get_commits(self, do_files: bool = False):
        """Fetch the commits associated with the pull request."""
        commits = self.gh_obj.get_commits()
        commits = progress_bar(
            commits, total=commits.totalCount,
            description=f"-- Fetching commits for PR#{self.number}"
        )

        res = []
        for commit in commits:
            commit_obj = GithubCommit.create_from_obj(commit, foreign={'repository': self.repository})
            res.append(commit_obj)
            commit_obj.get_parents()  # Fetch parent commits
            if do_files:
                commit_obj.get_files(pull_request=self)

        self.update_related('commits', res)
        return res

    def get_participants(self) -> list[GithubUser]:
        """Fetch the participants data for the issue."""
        raise NotImplementedError('Need to implement participation from both commenters and other')

    def get_gh_obj(self) -> gh_api.PullRequest:
        """
        Fetch the GitHub pull request object using the provided GitHub instance.
        This method is used to ensure that the GitHub pull request object is always up-to-date.
        """
        return self.repository.gh_obj.get_pull(self.number)

class GithubPRReview(GithubMixin[gh_api.PullRequestReview]):
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
        # Apparently some review can return user=None (e.g. easybuilders/easybuild-easyconfigs #3161)
        # Bug in PyGithub or wierd behavior in the API? -> default None to avoid error
        ColObjMap('created_by', 'user.login', default=None, converter=GithubUser.from_username),
        ColObjMap('state', 'state'),
        ColObjMap('submitted_at', 'submitted_at'),
    ]

    def __str__(self):
        return f"{self.pull_request} : {self.body[:30]} ({self.state})"

class GithubFile(GithubMixin[gh_api.File]):
    """Model representing a file in a GitHub repository."""
    # See https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests-files
    filename = models.CharField(max_length=512)
    prev_name = models.CharField(
        max_length=512, blank=True, null=True,
        help_text='Previous name of the file if renamed'
    )

    sha = models.CharField(max_length=40, null=True, blank=True, help_text='SHA of the file from github')

    status = models.CharField(
        max_length=20, choices=[
            ('added', 'Added'),
            ('removed', 'Removed'),
            ('modified', 'Modified'),
            ('renamed', 'Renamed'),
            ('copied', 'Copied'),
            ('changed', 'Changed'),
            ('unchanged', 'Unchanged')
        ]
    )

    additions = models.PositiveIntegerField(default=0)
    deletions = models.PositiveIntegerField(default=0)
    changes = models.PositiveIntegerField(default=0)

    blob_url = models.URLField(max_length=512)
    # raw_url = models.URLField(max_length=512)
    contents_url = models.URLField(max_length=512)

    patch = models.FileField(blank=True, null=True, help_text='Patch for the file changes')
    content = models.FileField(blank=True, null=True, help_text='Content of the file')

    pull_request = models.ForeignKey(
        GithubPullRequest, related_name='files', on_delete=models.CASCADE, null=True, blank=True
    )
    commit = models.ForeignKey(
        GithubCommit, related_name='files', on_delete=models.CASCADE, null=True, blank=True
    )

    id_key = None
    url_key = 'raw_url'

    obj_col_map =[
        ColObjMap('filename', 'filename'),
        ColObjMap('prev_name', 'previous_filename', default=None),
        ColObjMap('sha', 'sha'),
        ColObjMap('status', 'status'),
        ColObjMap('additions', 'additions', default=0),
        ColObjMap('deletions', 'deletions', default=0),
        ColObjMap('changes', 'changes', default=0),

        ColObjMap('blob_url', 'blob_url'),
        # ColObjMap('raw_url', 'raw_url'),
        ColObjMap('contents_url', 'contents_url'),

        ColObjMap(
            'patch', 'patch',
            converter=lambda x: ContentFile(x.encode('utf-8'), name='file.txt') if x else None
        )
    ]

    def fetch_content(self):
        """Fetch the content of the file from GitHub."""
        raise NotImplementedError()  # Need to check here to go through the RestAPI with the token


class GithubGist(GithubMixin[gh_api.Gist]):
    """Model representing a GitHub Gist."""
    description = models.TextField(blank=True, null=True)

    public = models.BooleanField(default=False)
    owner = models.ForeignKey(
        GithubUser, related_name='gists', on_delete=models.CASCADE, null=True, blank=True
    )

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    obj_col_map = [
        ColObjMap('description', 'description', default=None),
        ColObjMap('public', 'public', default=False),
        ColObjMap('owner', 'owner.login', converter=GithubUser.from_username),
        ColObjMap('created_at', 'created_at'),
        ColObjMap('updated_at', 'updated_at'),
    ]

    def fetch_files(self):
        """
        Fetch all files associated with this Gist.
        Returns a list of GithubGistFile instances.
        """
        files = self.gh_obj.files
        files = progress_bar(
            files, total=len(files),
            description=f"Fetching files for Gist {self.id} ({self.description or 'No description'})"
        )
        res = []
        for _, file_obj in files.items():
            gist_file = GithubGistFile.create_from_obj(file_obj, foreign={'gist': self})
            res.append(gist_file)
        return res

class GithubGistFile(GithubMixin[gh_api.GistFile]):
    """Model representing a file in a GitHub Gist."""

    filename = models.CharField(max_length=512)
    language = models.CharField(max_length=255, blank=True, null=True)
    # raw_url = models.URLField(max_length=512)
    size = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=128, blank=True, null=True, help_text='Type of the file (e.g., text/plain)')

    content = models.FileField(
        blank=True, null=True, help_text='Content of the file'
    )

    gist = models.ForeignKey(
        GithubGist, related_name='files', on_delete=models.CASCADE, null=True, blank=True
    )

    id_key = None
    url_key = 'raw_url'

    obj_col_map = [
        ColObjMap('filename', 'filename'),
        ColObjMap('language', 'language', default=None),
        # ColObjMap('raw_url', 'raw_url'),
        ColObjMap('size', 'size', default=0),
        ColObjMap('type', 'type', default=''),

        ColObjMap(
            'content', 'content',
            converter=lambda x: ContentFile(x.encode('utf-8'), name='file.txt') if x else None
        )
    ]
