from __future__ import absolute_import
from functools import partial
import json
import datetime

import six
from colander import (
    SchemaNode, Mapping, Sequence, Length, String, null, Invalid
)

from daybed.backends.exceptions import ModelNotFound
from . import registry, TypeFieldNode


class DefinitionSchema(SchemaNode):
    def __init__(self):
        super(DefinitionSchema, self).__init__(Mapping())
        self.add(SchemaNode(String(), name='title'))
        self.add(SchemaNode(String(), name='description'))
        self.add(SchemaNode(Sequence(), SchemaNode(TypeFieldNode()),
                            name='fields', validator=Length(min=1)))


class RolesSchema(SchemaNode):
    def __init__(self):
        super(RolesSchema, self).__init__(Mapping(unknown='preserve'))
        self.add(SchemaNode(Sequence(), SchemaNode(String()),
                            name='admins', validator=Length(min=1)))

        # XXX Control that the values of the sequence are valid tokens.
        # (we need to merge master to fix this. see #86)


class RecordSchema(SchemaNode):
    def __init__(self, definition):
        super(RecordSchema, self).__init__(Mapping())
        for field in definition['fields']:
            fieldtype = field.pop('type')
            self.add(registry.validation(fieldtype, **field))


def validate_against_schema(request, schema, data):
    try:
        data_pure = schema.deserialize(data)
        data_clean = post_serialize(data_pure)
        # Attach data_clean to request: see usage in views.
        request.data_clean = data_clean
    except Invalid as e:
        for error in e.children:
            # here we transform the errors we got from colander into cornice
            # errors
            for field, error in error.asdict().items():
                request.errors.add('body', field, error)


def post_serialize(data):
    """Returns the most agnostic version of specified data.
    (remove colander notions, datetimes in ISO, ...)
    """
    clean = dict()
    for k, v in data.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            clean[k] = v.isoformat()
        elif v is null:
            pass
        else:
            clean[k] = v
    return clean


def validator(request, schema):
    """Validates the request according to the given schema"""
    try:
        body = request.body.decode('utf-8')
        dictbody = json.loads(body) if body else {}
        validate_against_schema(request, schema, dictbody)
    except ValueError as e:
        request.errors.add('body', 'body', six.text_type(e))


#  Validates a request body according model definition schema.
definition_validator = partial(validator, schema=DefinitionSchema())


def record_validator(request):
    """Validates a request body according to its model definition.
    """
    model_id = request.matchdict['model_id']

    try:
        definition = request.db.get_model_definition(model_id)
        schema = RecordSchema(definition)
        validator(request, schema)
    except ModelNotFound:
        request.errors.add('path', 'modelname',
                           'Unknown model %s' % model_id)
        request.errors.status = 404


def model_validator(request):
    """Verify that the model is okay (that we have the right fields) and
    eventually populates it if there is a need to.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except ValueError:
        request.errors.add('body', 'json value error', "body malformed")
        return

    # Check the definition is valid.
    definition = body.get('definition')
    if not definition:
        request.errors.add('body', 'definition', 'definition is required')
    else:
        validate_against_schema(request, DefinitionSchema(), definition)
    request.validated['definition'] = definition

    # Check that the records are valid according to the definition.
    records = body.get('records')
    request.validated['records'] = []
    if records:
        definition_schema = RecordSchema(definition)
        for record in records:
            validate_against_schema(request, definition_schema, record)
            request.validated['records'].append(record)


def token_validator(request):
    """Verify that the model is okay (that we have the right fields) and
    eventually populates it if there is a need to.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except ValueError:
        request.errors.add('body', 'json value error', "body malformed")
        return

    # Check the definition is valid.
    definition = body.get('definition')
    if not definition:
        request.errors.add('body', 'definition', 'definition is required')
    else:
        validate_against_schema(request, DefinitionSchema(), definition)
    request.validated['definition'] = definition

    # Check that the records are valid according to the definition.
    records = body.get('records')
    request.validated['records'] = []
    if records:
        definition_schema = RecordSchema(definition)
        for record in records:
            validate_against_schema(request, definition_schema, record)
            request.validated['records'].append(record)
