# -*- coding: utf-8 -*-
from collections import defaultdict
from pyramid.interfaces import IAuthorizationPolicy
from pyramid.security import Authenticated, Everyone
from zope.interface import implementer

from daybed.backends.exceptions import (
    ModelNotFound, RecordNotFound, TokenNotFound
)
from daybed import logger

PERMISSIONS_SET = set([
    'read_definition', 'read_acls', 'update_definition', 'update_acls',
    'delete_model',
    'create_record',
    'read_all_records', 'update_all_records', 'delete_all_records',
    'read_my_record', 'update_my_record', 'delete_my_record'
])


def get_model_acls(token, permissions_list=PERMISSIONS_SET, acls=None):
    # - Add the token to given acls.
    # - By default give all permissions to the token
    # - You can pass existing acls if you want to add the token to some
    # permissions
    if acls is None:
        acls = defaultdict(list)
    else:
        acls = defaultdict(list, **acls)

    for perm in permissions_list:
        acls[perm].append(token)

    return acls


class Any(list):
    def matches(self, permissions):
        check = False
        for perm in self:
            if hasattr(perm, 'matches'):
                check |= perm.matches(permissions)
            else:
                check |= perm in permissions
        return check


class All(list):
    def matches(self, permissions):
        check = True
        for perm in self:
            if hasattr(perm, 'matches'):
                check &= perm.matches(permissions)
            else:
                check &= perm in permissions
        return check


AUTHORS_PERMISSIONS = set(['update_my_record', 'delete_my_record',
                           'read_my_record'])

VIEWS_PERMISSIONS_REQUIRED = {
    'post_model':     All(['create_model']),
    'get_model':      All(['read_definition', 'read_acls']),
    'put_model':      All(['create_model', 'update_definition', 'update_acls',
                           'delete_model']),
    'delete_model':   All(['delete_model']),
    'get_definition': All(['read_definition']),
    'post_record':    All(['create_record']),
    'get_records':    All(['read_all_records']),
    'delete_records': All(['delete_all_records']),
    'get_record':     Any(['read_my_record', 'read_all_records']),
    'put_record':     All(['create_record',
                           Any(['update_my_record', 'update_all_records']),
                           Any(['delete_my_record', 'delete_all_records'])]),
    'patch_record':   Any(['update_my_record', 'update_all_records']),
    'delete_record':  Any(['delete_my_record', 'delete_all_records']),
}


@implementer(IAuthorizationPolicy)
class DaybedAuthorizationPolicy(object):

    def __init__(self, model_creators=None):
        if model_creators is None:
            model_creators = "Everyone"

        self.model_creators = set(model_creators)

        # Handle Pyramid constants.
        if "Authenticated" in self.model_creators:
            self.model_creators.remove("Authenticated")
            self.model_creators.add(Authenticated)

        if "Everyone" in self.model_creators:
            self.model_creators.remove("Everyone")
            self.model_creators.add(Everyone)

    def permits(self, context, principals, permission):
        """Returns True or False depending if the token with the specified
        principals has access to the given permission.
        """
        permissions_required = VIEWS_PERMISSIONS_REQUIRED[permission]

        token_permissions = set()
        can_create_model = self.model_creators & set(principals) != set()

        if can_create_model:
            token_permissions.add("create_model")

        if context.model_id:
            try:
                acls = context.db.get_model_acls(context.model_id)
            except ModelNotFound:
                # PUT a non existing model
                return can_create_model
        else:
            # POST a model
            return can_create_model

        for acl_name, tokens in acls.items():
            # If one of the principals is in the valid tokens for this,
            # permission, grant the permission.
            if set(principals) & set(tokens):
                token_permissions.add(acl_name)

        logger.debug("token permissions: %s", token_permissions)

        if context.record_id is not None:
            try:
                authors = context.db.get_record_authors(
                    context.model_id, context.record_id)
            except RecordNotFound:
                authors = []
            finally:
                if not set(principals) & set(authors):
                    token_permissions -= AUTHORS_PERMISSIONS

        # Check view permission matches token permissions.
        return permissions_required.matches(token_permissions)

    def principals_allowed_by_permission(self, context, permission):
        raise NotImplementedError()  # PRAGMA NOCOVER


class RootFactory(object):
    def __init__(self, request):
        self.db = request.db
        matchdict = request.matchdict or {}
        self.model_id = matchdict.get('model_id')
        self.record_id = matchdict.get('record_id')
        self.request = request


def build_user_principals(token, request):
    return [token]


def check_api_token(token, password, request):
    try:
        token = request.db.get_token(token)
        if token['apitoken'] == password:
            return build_user_principals(token, request)
        return []
    except TokenNotFound:
        return []
