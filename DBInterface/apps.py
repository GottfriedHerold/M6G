from django.apps import AppConfig
import logging
logger = logging.getLogger('chargen.database.apps')

class DbinterfaceConfig(AppConfig):
    name = 'DBInterface'

    is_ready = False

    def ready(self):
        super().ready()  # this actually does nothing
        if not DbinterfaceConfig.is_ready:
            DbinterfaceConfig.is_ready = True
            logger.info('DBInterface is ready')
            from . import signals
