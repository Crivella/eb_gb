"""GitHub-related models for Django application."""
import os

from django.db import models

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', None)
# if not GITHUB_TOKEN:
#     raise ValueError('GITHUB_TOKEN environment variable is not set. Please set it to use GitHub-related features.')


class GithubMixin(models.Model):
    """
    Mixin for common fields used in GitHub-related models.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @classmethod
    def from_dct(cls, dct, allow_new=False):
        """
        Create or update an instance from a dictionary.
        If the instance does not exist and allow_new is True, create a new instance.
        """
        instance = cls.objects.filter(**dct).first()
        if not instance:
            if allow_new:
                instance = cls(**dct)
                instance.save()
            else:
                raise ValueError(f"{cls.__name__} with {dct} does not exist.")
        return instance

class GithubUser(GithubMixin):
    """Model representing a GitHub user."""
    username = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    avatar_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.username

class GithubRepository(GithubMixin):
    """Model representing a GitHub repository."""
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(GithubUser, related_name='repositories', on_delete=models.CASCADE)
    description = models.TextField(blank=True, null=True)
    url = models.URLField()

    def __str__(self):
        return f"{self.name} by {self.owner.username}"

class GithubIssue(GithubMixin):
    """Model representing a GitHub issue."""
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    repository = models.ForeignKey(GithubRepository, related_name='issues', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Issue: {self.title} in {self.repository.name}"

class GithubPullRequest(GithubMixin):
    """Model representing a GitHub Pull Request."""
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    repository = models.ForeignKey(GithubRepository, related_name='pull_requests', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_merged = models.BooleanField(default=False)

    def __str__(self):
        return f"PR: {self.title} in {self.repository.name}"
