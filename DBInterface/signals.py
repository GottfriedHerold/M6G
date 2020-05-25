import logging
signal_logger = logging.getLogger('chargen.database.signals')
model_logger = logging.getLogger('chargen.database.models')
user_logger = logging.getLogger('chargen.database.users')

signal_logger.info('Registering signals')

from django.db.models.signals import post_save, m2m_changed
from .models import CGUser
from django.dispatch import receiver

@receiver(post_save, sender=CGUser)
def user_has_changed(sender, **kwargs):
    user_logger.info("A CGUser entry was saved to the database. Params: %s", kwargs)