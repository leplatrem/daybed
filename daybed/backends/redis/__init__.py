import json
import redis

from daybed.backends.exceptions import (
    TokenAlreadyExist, TokenNotFound, ModelNotFound, RecordNotFound
)


class RedisBackend(object):

    @classmethod
    def load_from_config(cls, config):
        settings = config.registry.settings
        generator = config.maybe_dotted(settings['daybed.id_generator'])
        return RedisBackend(
            settings['backend.db_host'],
            settings['backend.db_port'],
            settings['backend.db_index'],
            generator(config)
        )

    def __init__(self, host, port, db, id_generator):
        # model id generator
        self._db = redis.StrictRedis(host=host, port=port, db=db)
        self._db.ping()
        self._generate_id = id_generator

    def delete_db(self):
        self._db.flushdb()

    def __get_model(self, model_id):
        model = self._db.get("model.%s" % model_id)
        if model is not None:
            return model.decode("utf-8")
        raise ModelNotFound(model_id)

    def get_model_definition(self, model_id):
        model = self.__get_model(model_id)
        return json.loads(model)['definition']

    def get_model_acls(self, model_id):
        doc = self.__get_model(model_id)
        return json.loads(doc)['acls']

    def __get_records(self, model_id):
        # Check if the model still exists or raise
        self.__get_model(model_id)

        model_records = self._db.smembers(
            "model.%s.records" % model_id
        )
        if model_records:
            return self._db.mget(*model_records)
        else:
            return []

    def get_records(self, model_id):
        records = []
        for item in self.__get_records(model_id):
            records.append(json.loads(item.decode("utf-8"))['record'])
        return records

    def __get_record(self, model_id, record_id):
        record = self._db.get("model.%s.record.%s" % (model_id, record_id))
        if record is not None:
            return record.decode("utf-8")
        raise RecordNotFound(u'(%s, %s)' % (model_id, record_id))

    def get_record(self, model_id, record_id):
        doc = self.__get_record(model_id, record_id)
        return json.loads(doc)['record']

    def get_record_authors(self, model_id, record_id):
        doc = self.__get_record(model_id, record_id)
        return json.loads(doc)['authors']

    def put_model(self, definition, acls, model_id=None):
        if model_id is None:
            model_id = self._generate_id()

        self._db.set(
            "model.%s" % model_id,
            json.dumps({
                'definition': definition,
                'acls': acls
            })
        )
        self._db.delete("model.%s.records" % model_id)
        return model_id

    def put_record(self, model_id, record, authors, record_id=None):
        doc = {
            'authors': authors,
            'record': record
        }

        if record_id is not None:
            try:
                old_doc = json.loads(self.__get_record(model_id, record_id))
            except RecordNotFound:
                pass
            else:
                authors = list(set(authors) | set(old_doc['authors']))
                doc['authors'] = authors
                old_doc.update(doc)
                doc = old_doc
        else:
            record_id = self._generate_id()

        self._db.set(
            "model.%s.record.%s" % (model_id, record_id),
            json.dumps(doc)
        )
        self._db.sadd(
            "model.%s.records" % model_id,
            "model.%s.record.%s" % (model_id, record_id)
        )
        return record_id

    def delete_record(self, model_id, record_id):
        doc = self.__get_record(model_id, record_id)
        if doc:
            self._db.delete("model.%s.record.%s" % (model_id, record_id))
            self._db.srem(
                "model.%s.records" % model_id,
                "model.%s.record.%s" % (model_id, record_id)
            )
            return json.loads(doc)

    def delete_records(self, model_id):
        records = self.get_records(model_id)
        existing_records_keys = [
            "model.%s.record.%s" % (model_id, r.id) for r in records
        ]
        existing_records_keys.append("model.%s.records" % model_id)

        self._db.delete(existing_records_keys)
        return records

    def delete_model(self, model_id):
        doc = json.loads(self.__get_model(model_id))
        doc["records"] = self.delete_records(model_id)
        self._db.delete("model.%s" % model_id)
        return doc

    def __get_token(self, tokenHmacId):
        secret = self._db.get("token.%s" % tokenHmacId)
        if secret is None:
            raise TokenNotFound(tokenHmacId)
        return secret.decode("utf-8")

    def get_token(self, tokenHmacId):
        """Returns the information associated with an token"""
        return self.__get_token(tokenHmacId)

    def add_token(self, tokenHmacId, secret):
        # Check that the token doesn't already exist.
        try:
            self.__get_token(tokenHmacId)
            raise TokenAlreadyExist(tokenHmacId)
        except TokenNotFound:
            pass

        self._db.set("token.%s" % tokenHmacId, secret)
