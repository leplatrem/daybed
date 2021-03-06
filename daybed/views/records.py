import json

from cornice import Service
from pyramid.security import Everyone

from daybed.backends.exceptions import RecordNotFound
from daybed.schemas.validators import (RecordValidator, record_validator,
                                       validate_against_schema)


records = Service(name='records',
                  path='/models/{model_id}/records',
                  description='Collection of records',
                  renderer='jsonp')


record = Service(name='record',
                 path='/models/{model_id}/records/{record_id}',
                 description='Single record',
                 renderer="jsonp")


@records.get(permission='get_records')
@records.get(accept='application/geojson', renderer='geojson',
             permission='get_records')
def get_records(request):
    """Retrieves all model records."""
    model_id = request.matchdict['model_id']
    # Check that model is defined
    exists = request.db.get_model_definition(model_id)
    if not exists:
        request.response.status = "404 Not Found"
        return {"msg": "%s: model not found" % model_id}
    # Return array of records
    results = request.db.get_records(model_id)
    return {'data': results}


@records.post(validators=record_validator, permission='post_record')
def post_record(request):
    """Saves a single model record.

    Posted record attributes will be matched against the related model
    definition.

    """
    # if we are asked only for validation, don't do anything more.
    if request.headers.get('X-Daybed-Validate-Only', 'false') == 'true':
        return

    model_id = request.matchdict['model_id']
    if request.user:
        username = request.user['name']
    else:
        username = Everyone
    record_id = request.db.put_record(model_id, request.data_clean,
                                      username)
    created = u'%s/models/%s/records/%s' % (request.application_url, model_id,
                                            record_id)
    request.response.status = "201 Created"
    request.response.headers['location'] = str(created)
    return {'id': record_id}


@records.delete(permission='delete_records')
def delete_records(request):
    """Deletes all records of model."""
    model_id = request.matchdict['model_id']
    request.db.delete_records(model_id)
    return {"msg": "ok"}


@record.get(permission='get_record')
def get(request):
    """Retrieves a singe record."""
    model_id = request.matchdict['model_id']
    record_id = request.matchdict['record_id']
    try:
        return request.db.get_record(model_id, record_id)
    except RecordNotFound:
        request.response.status = "404 Not Found"
        return {"msg": "%s: record not found %s" % (model_id, record_id)}


@record.put(validators=record_validator, permission='put_record')
def put(request):
    """Updates or creates a record."""
    model_id = request.matchdict['model_id']
    record_id = request.matchdict['record_id']

    if request.user:
        username = request.user['name']
    else:
        username = Everyone

    record_id = request.db.put_record(model_id, request.data_clean,
                                      [username], record_id=record_id)
    return {'id': record_id}


@record.patch(permission='patch_record')
def patch(request):
    """Updates an existing record."""
    model_id = request.matchdict['model_id']
    record_id = request.matchdict['record_id']

    if request.user:
        username = request.user['name']
    else:
        username = Everyone

    try:
        data = request.db.get_record(model_id, record_id)
    except RecordNotFound:
        request.response.status = "404 Not Found"
        return {"msg": "%s: record not found %s" % (model_id, record_id)}

    data.update(json.loads(request.body.decode('utf-8')))
    definition = request.db.get_model_definition(model_id)
    validate_against_schema(request, RecordValidator(definition), data)
    if not request.errors:
        request.db.put_record(model_id, data, [username], record_id)
    return {'id': record_id}


@record.delete(permission='delete_record')
def delete(request):
    """Deletes a record."""
    model_id = request.matchdict['model_id']
    record_id = request.matchdict['record_id']

    try:
        deleted = request.db.delete_record(model_id, record_id)
    except RecordNotFound:
        request.response.status = "404 Not Found"
        return {"msg": "%s: record not found %s" % (model_id, record_id)}
    return deleted
