import os
import socket

from couchdb.client import Server
from couchdb.http import PreconditionFailed
from couchdb.design import ViewDefinition

from daybed import logger
from .views import docs
from .database import Database


class CouchDBBackendConnectionError(Exception):
    pass


class CouchDBBackend(object):
    def db(self):
        return Database(self.server[self.db_name], self._generate_id)

    def __init__(self, config):
        settings = config.registry.settings

        self.config = config
        self.server = Server(settings['backend.db_host'])
        self.db_name = os.environ.get('DB_NAME', settings['backend.db_name'])

        # model id generator
        generator = config.maybe_dotted(settings['daybed.id_generator'])
        self._generate_id = generator(config)

        try:
            self.create_db_if_not_exist()
        except socket.error as e:
            raise CouchDBBackendConnectionError(
                "Unable to connect to the CouchDB server: %s - %s" % (
                    settings['backend.db_host'], e))

        self.sync_views()

    def delete_db(self):
        del self.server[self.db_name]

    def create_db_if_not_exist(self):
        try:
            self.server.create(self.db_name)
            logger.info('Creating and using db "%s"' % self.db_name)
        except PreconditionFailed:
            logger.info('Using db "%s".' % self.db_name)

    def sync_views(self):
        ViewDefinition.sync_many(self.server[self.db_name], docs)
