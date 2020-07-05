from typing import Optional, Union
import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction

from .user_model import CGUser, CGGroup
from .char_models import CharModel, CharVersionModel
from .meta import MyMeta, MANAGER_TYPE

user_logger = logging.getLogger('chargen.database.users')


# permissions set on a user level. Do not use directly.
class UserPermissionsForChar(models.Model):
    class Meta(MyMeta):
        constraints = [
            models.UniqueConstraint(fields=['char', 'user'], name='m2muserperms'),
            models.CheckConstraint(check=models.Q(may_read__gte=models.F('may_write')), name='user_write_implies_read'),
        ]
        indexes = [models.Index(fields=['char', 'user'])]
    char: CharModel = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='direct_user_permissions')
    user: CGUser = models.ForeignKey(CGUser, on_delete=models.CASCADE, related_name='direct_char_permissions')
    may_read: bool = models.BooleanField(default=True)
    may_write: bool = models.BooleanField(default=True)

    objects: 'MANAGER_TYPE[UserPermissionsForChar]'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        CharUsers.update_char_user(char=self.char, user=self.user)

    @staticmethod
    def user_permission_deleted_for_char_signal(sender: type, **kwargs):
        assert sender is UserPermissionsForChar
        instance: UserPermissionsForChar = kwargs['instance']
        instance.may_write = False
        instance.may_read = False
        instance.save()

    def __str__(self) -> str:
        d = {'char_name': str(self.char), 'user_name': str(self.user)}
        if self.may_write:
            return "user-level write permission for char %(char_name)s and user %(user_name)s" % d
        elif self.may_read:
            return "user-level read permission for char %(char_name)s and user %(user_name)s" % d
        else:
            return "user-level empty permission for char %(char_name)s and user %(user_name)s" % d


class GroupPermissionsForChar(models.Model):
    class Meta(MyMeta):
        constraints = [
            models.UniqueConstraint(fields=['char', 'group'], name='m2mgroupperms'),
            models.CheckConstraint(check=models.Q(may_read__gte=models.F('may_write')), name='group_write_implies_read'),
        ]
        indexes = [models.Index(fields=['char', 'group'])]
    char: CharModel = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='group_permissions')
    group: CGGroup = models.ForeignKey(CGGroup, on_delete=models.CASCADE, related_name='char_permissions')
    may_read: bool = models.BooleanField(default=True)
    may_write: bool = models.BooleanField(default=True)

    objects: 'MANAGER_TYPE[GroupPermissionsForChar]'
    affected_char_permissions: 'MANAGER_TYPE[CharUsers]'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        for user in self.group.users.all():
            CharUsers.update_char_user(char=self.char, user=user)

    @staticmethod  # pre-delete in signals.py
    def group_permissions_deleted_for_char_signal(sender: type, **kwargs):
        assert sender is GroupPermissionsForChar
        instance: GroupPermissionsForChar = kwargs['instance']
        user_logger.debug("Dropping permissions for group/char-pair: %s", instance)
        instance.may_write = False
        instance.may_read = False
        instance.save()

    def __str__(self) -> str:
        d = {'char_name': str(self.char), 'group_name': str(self.group)}
        if self.may_write:
            return "group-level write permission for char %(char_name)s and group %(group_name)s" % d
        elif self.may_read:
            return "group-level read permission for char %(char_name)s and group %(group_name)s" % d
        else:
            return "group-level empty permission for char %(char_name)s and group %(group_name)s" % d


class CharUsers(models.Model):
    """
        Entries for every (char, user)-pair for which user has at least some permissions for char.
        This includes indirect permissions through group membership and is synchronized with user-level and group-level
        permissions. Also stores other relevant data for the pair: at the moment, the last opened char version.
    """
    class Meta(MyMeta):
        constraints = [
            models.UniqueConstraint(fields=['char', 'user'], name='m2mcharuser'),
            models.CheckConstraint(check=models.Q(true_read_permission__gte=models.F('true_write_permission')), name='write_implies_read'),
            # This implies the above, but that's really an implementation detail.
            models.CheckConstraint(check=models.Q(true_read_permission=True), name='can_always_read'),
        ]
        indexes = [models.Index(fields=['char', 'user'])]
    char: CharModel = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='user_data_set')
    user: CGUser = models.ForeignKey(CGUser, on_delete=models.CASCADE, related_name='char_data_set')
    opened_version: Optional[CharVersionModel] = models.ForeignKey(CharVersionModel, on_delete=models.SET_NULL, null=True, related_name='+')
    # name true_ is to indicate that it includes both user-level and group-level permissions
    true_read_permission: bool = models.BooleanField()  # will actually always be true if saved in db.
    true_write_permission: bool = models.BooleanField()

    # If user has permissions for char *because* user belongs to a group, this is recorded here,
    # i.e. group_reason is a group that is responsible for highest permission level.
    # If user-level permissions are responsible, this is null, if permissions via user and group are the same, we
    # prefer null (Technically, it is mandatory that group_reason does not refer to a group that gives no permissions)
    # The purpose of group_reason is to simplify synchronization with User / Group permissions
    # and safeguard against some bugs.
    group_reason: Optional[GroupPermissionsForChar] = models.ForeignKey(GroupPermissionsForChar,
                                                                        on_delete=models.PROTECT,
                                                                        null=True,
                                                                        related_name='affected_char_permissions')
    objects: 'MANAGER_TYPE[CharUsers]'

    @staticmethod
    def update_char_user(*, char: CharModel, user: 'CGUser') -> Optional['CharUsers']:
        """
        This creates / updates a CharUsers entry in the database for char and user and returns the new object.
        We opt to delete the corresponding object if no permissions are present.
        """

        user_logger.info('Updating permissions for char %(char)s and user %(user)s' % {'char': char, 'user': user})
        with transaction.atomic():
            char_user: 'CharUsers'
            try:
                char_user = CharUsers.objects.get(char=char, user=user)
                user_logger.info('Pre-existing permission')
                create = False
            except ObjectDoesNotExist:
                char_user = CharUsers(char=char, user=user, opened_version=None, true_read_permission=False,
                                      true_write_permission=False, group_reason=None)
                user_logger.info('Created new permissions')
                create = True
            try:
                user_perms: UserPermissionsForChar = UserPermissionsForChar.objects.get(char=char, user=user)
                if user_perms.may_write:
                    char_user.true_read_permission = True
                    char_user.true_write_permission = True
                    char_user.group_reason = None
                    char_user.save()
                    user_logger.info('User may write due to user-level permissions')
                    return char_user
                user_read: bool = user_perms.may_read
            except ObjectDoesNotExist:
                user_read: bool = False

            g = GroupPermissionsForChar.objects.filter(char=char).filter(may_write=True).filter(group__users__pk=user.pk).first()
            if g:
                char_user.true_write_permission = True
                char_user.true_read_permission = True
                char_user.group_reason = g
                char_user.save()
                user_logger.info('User may write due to group-level permissions')
                return char_user
            char_user.true_write_permission = False
            if user_read:
                char_user.true_read_permission = True
                char_user.group_reason = None
                char_user.save()
                user_logger.info('user may read due to user-level permissions')
                return char_user
            g = GroupPermissionsForChar.objects.filter(char=char).filter(may_read=True).filter(group__users__pk=user.pk).first()
            if g:
                char_user.true_read_permission = True
                char_user.group_reason = g
                char_user.save()
                user_logger.info('user may read due to group-level permissions')
                return char_user
            elif not create:
                char_user.delete()
                user_logger.info('deleted pre-existing permissions object')
            user_logger.info('no permissions granted to user')
            return None

    @staticmethod
    def recompute_all_char_user_permissions():
        with transaction.atomic():  # to guard against change of CGUsers.objects.all()
            users = list(CGUser.objects.all())
            for char in CharModel.objects.all():
                for user in users:
                    CharUsers.update_char_user(char=char, user=user)

    # use this (or the shortcuts on CGChar, CharModel, CharVersionModel) exclusively as out-facing interface.

    @classmethod
    def user_may_read(cls, *, char: Union[CharModel, CharVersionModel], user: CGUser) -> bool:
        """
        Checks whether user has read access to char. This is the preferred interface to use.
        (or the shortcuts in CGUser, CharModel, CharVersionModel)
        """
        if user.is_admin:
            return True
        if isinstance(char, CharModel):
            return cls.objects.filter(char=char, user=user, true_read_permission=True).exists()
        else:
            assert isinstance(char, CharVersionModel)
            return cls.objects.filter(char=char.owner, user=user, true_read_permission=True).exists()

    @classmethod
    def user_may_write(cls, *, char: Union[CharModel, CharVersionModel], user: CGUser) -> bool:
        """
        Checks whether user has read/write access to char. This is the preferred interface to use.
        (or the shortcuts in CGUser, CharModel, CharVersionModel)
        """

        if user.is_admin:
            return True
        if isinstance(char, CharModel):
            return cls.objects.filter(char=char, user=user, true_write_permission=True).exists()
        else:
            assert isinstance(char, CharVersionModel)
            return cls.objects.filter(char=char.owner, user=user, true_write_permission=True).exists()
