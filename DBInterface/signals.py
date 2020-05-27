import logging
from django.db.models.signals import post_save, pre_delete, m2m_changed
from .models import CGUser, CharVersionModel
from django.dispatch import receiver
from django.db import transaction

signal_logger = logging.getLogger('chargen.database.signals')
model_logger = logging.getLogger('chargen.database.models')
user_logger = logging.getLogger('chargen.database.users')

signal_logger.info('Registering signals')


# noinspection PyUnusedLocal
@receiver(post_save, sender=CGUser)
def user_has_changed(sender: type, **kwargs):
    user_logger.info("A CGUser entry was saved to the database. Params: %s", kwargs)

@receiver(pre_delete, sender=CharVersionModel)
def ensure_rooted_tree(sender: type, **kwargs):
    model_logger.info("About to delete CharVersion. Params: %s", kwargs)
    instance = kwargs['instance']
    with transaction.atomic():
        for child in instance.children.all():
            child: CharVersionModel
            child.parent = instance.parent
            child.save()
