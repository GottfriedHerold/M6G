import logging
from django.db.models.signals import post_save, pre_delete, m2m_changed
from .models import CGUser, CharVersionModel, GroupPermissionsForChar, UserPermissionsForChar, CharUsers
from django.dispatch import receiver
from django.db import transaction

signal_logger = logging.getLogger('chargen.database.signals')
model_logger = logging.getLogger('chargen.database.models')
user_logger = logging.getLogger('chargen.database.users')

signal_logger.info('Registering signals')


# noinspection PyUnusedLocal
@receiver(post_save, sender=CGUser)
def user_has_changed(sender: type, **kwargs):
    user_logger.info("A CGUser entry was saved to the database. Name: %s", kwargs['instance'])

@receiver(pre_delete, sender=CharVersionModel)
def ensure_rooted_tree(sender: type, **kwargs):
    instance = kwargs['instance']
    model_logger.info("About to delete CharVersion. Name: %s. Fixing Tree structure", instance)
    with transaction.atomic():
        for child in instance.children.all():
            child: CharVersionModel
            child.parent = instance.parent
            child.save()


pre_delete.connect(GroupPermissionsForChar.group_permissions_deleted_for_char_signal, sender=GroupPermissionsForChar)
pre_delete.connect(UserPermissionsForChar.user_permission_deleted_for_char_signal, sender=UserPermissionsForChar)

@receiver(m2m_changed, sender=GroupPermissionsForChar)
def update_group_permissions_for_char_m2m(sender: type, **kwargs):
    raise RuntimeError("Change group permissions by modifying GroupPermissionsForChar objects directly")

@receiver(m2m_changed, sender=UserPermissionsForChar)
def update_user_permissions_for_char_m2m(sender: type, **kwargs):
    raise RuntimeError("Change user permissions by modifying UserPermissionsForChar objects directly")

@receiver(m2m_changed, sender=CGUser.groups.through)
def changed_user_group_membership(sender: type, **kwargs):
    assert sender is CGUser.groups.through
    action: str = kwargs['action']
    if action == 'post_add' or action == 'post_clear' or action == 'post_remove':
        # Fine grained control is too error-prone.
        CharUsers.recompute_all_char_user_permissions()
