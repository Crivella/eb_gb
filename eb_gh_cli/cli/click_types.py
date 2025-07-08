# pylint: skip-file
import logging

import click
from click.shell_completion import CompletionItem
from django.db.models import Q

from .. import models as m

logger = logging.getLogger('gh_db')

class DjangoModelType(click.ParamType):
    """
    A custom Click parameter type for Django model instances.
    This type can be used to retrieve a model instance by its primary key.
    """
    query_param_name: str = None
    model_class: m.GithubMixin = None
    help = lambda x: str(x)

    filters = None

    def __init__(self, allow_new: bool = False, allow_list: bool = False):
        if self.model_class is None:
            raise ValueError('model_class must be set for DjangoModelType')
        if self.query_param_name is None:
            raise ValueError('query_param must be set for DjangoModelType')
        super().__init__()

        self.allow_new = allow_new
        self.allow_list = allow_list

    def convert(self, value, param, ctx):
        res = None

        update = getattr(ctx, 'hidden_params', {}).get('update', False)

        try:
            res = self.model_class.from_autocomplete_string(
                value,
                allow_new=self.allow_new,
                # allow_list=self.allow_list,
                update=update
            )
        except ValueError as e:
            self.fail(f'Item {self.model_class.__name__}<{value}> does not exists and cannot be created: ' + str(e), param, ctx)

        return res

    def shell_complete(self, ctx: click.Context, param: click.Parameter, incomplete: str):
        """Provide shell completion for DjangoModelType."""
        hidden_params = getattr(ctx, 'hidden_params', {})
        q = self.model_class.objects
        q = q.filter(self.model_class.filter_autocomplete_string(incomplete))

        filters = self.filters or {}
        for key, flt_func in filters.items():
            val = hidden_params.get(key, None)
            if val is None:
                continue
            q = q.filter(flt_func(val))

        choices = q.all()
        return [
            CompletionItem(
                # getattr(obj, self.query_param_name),
                obj.get_autocomplete_string(),
                help=str(obj)
            )
            for obj in choices
        ]

    def __repr__(self):
        return f'{self.__class__.__name__}({self.model_class.__name__}, {self.query_param_name})'

class GithubUserType(DjangoModelType):
    query_param_name = 'username'
    model_class = m.GithubUser

class GithubRepositoryType(DjangoModelType):
    query_param_name = 'name'
    model_class = m.GithubRepository

    filters = {
        'gh_user': lambda gh_user: Q(owner=gh_user),
    }

class GithubIssueType(DjangoModelType):
    query_param_name = 'number'
    model_class = m.GithubIssue

    filters = {
        'gh_user': lambda gh_user: (
            Q(created_by=gh_user) |
            Q(closed_by=gh_user) |
            Q(assignes__contains=gh_user) |
            Q(assignee=gh_user)
        ),
        'gh_repo': lambda gh_repo: Q(repository=gh_repo),
    }

class GithubPullRequestType(DjangoModelType):
    query_param_name = 'number'
    model_class = m.GithubPullRequest

    filters = {
        'gh_user': lambda gh_user: (
            Q(created_by=gh_user) |
            Q(closed_by=gh_user) |
            Q(assignees__contains=gh_user) |
            Q(assignee=gh_user)
        ),
        'gh_repo': lambda gh_repo: Q(repository=gh_repo),
    }
