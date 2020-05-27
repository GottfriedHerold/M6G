from django.apps import AppConfig
import logging
logger = logging.getLogger('chargen.database.apps')

class DBInterfaceConfig(AppConfig):
    name = 'DBInterface'

    is_ready = False

    def ready(self):
        super().ready()  # this actually does nothing
        if not DBInterfaceConfig.is_ready:
            DBInterfaceConfig.is_ready = True
            logger.info('DBInterface is ready')
            # noinspection PyUnresolvedReferences
            from . import signals  # This has side-effects!
