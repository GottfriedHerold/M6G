from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
import logging
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from typing import Optional, TypeVar, Generic, Iterator
from datetime import datetime

_Z = TypeVar('_Z')

class MANAGER_TYPE(Generic[_Z], models.QuerySet, models.Manager):
    def __iter__(self) -> Iterator[_Z]: ...

class RELATED_MANAGER_TYPE(MANAGER_TYPE[_Z]):
    def add(self, *obs, bulk=True, through_defaults=None): ...


logger = logging.getLogger('chargen.database')
user_logger = logging.getLogger('chargen.database.users')

# User model. Unfortunately, Django's default user model has its share of issues.

# Additionally, it can not be changed easily later, so we use our own CGUser model for user accounts.
# Unfortunately, Django's admin interfaces make several assumptions (with partial documentation spread all over the place)
# on the user interface. This affects the User model, the Model manager, the Permissions model, its relation to Groups,
# the manage.py command-line and the default admin forms that all make some forms of assumptions wrt each other.
# Furthermore, the permissions management (what chars can be viewed/edited by a specific user) that Django provides (and
# is used in the admin-interface) gives permissions on a per-model level and not per-instance. While there is an
# interface for per-model, it is a stub as of Django 3.0 (essentially everything needs to be subclassed and overridden
# with the parent class providing hardly any functionality).
# The following together with forms in admin.py is adapted from an example in the docs.

class CGUserManager(BaseUserManager):
    def create_user(self, username, email, password=None):
        """
            Creates a standard (non-admin) user
        """
        if not username:
            raise ValueError('Username is empty')
        user = self.model(username=username, email=email)
        user.set_password(password)
        user.save(using=self._db)
        user_logger.info('Created user with username %s', username)
        user.groups.add(get_default_group())
        return user

    def create_superuser(self, username, email, password=None):
        user = self.create_user(username=username, email=email, password=password)
        user.is_admin = True
        user.save(using=self._db)
        user_logger.critical('Turned user into superuser with username %s', username)
        return user

class CGUser(AbstractBaseUser):
    class Meta:
        default_permissions = ()
    username: str = models.CharField(max_length=40, unique=True)
    USERNAME_FIELD = 'username'  # database field that is used as username in the login.
    REQUIRED_FIELDS = ['email']  # list of additional mandatory fields queried in the "manage.py createsuperuser" script.
    objects: 'MANAGER_TYPE[CGUser]' = CGUserManager()  # object manager. We can't use the default one
    is_active: bool = models.BooleanField(default=True)
    is_admin: bool = models.BooleanField(default=False)
    email: str = models.EmailField(verbose_name='email address', max_length=255)
    groups: 'RELATED_MANAGER_TYPE[CGGroup]' = models.ManyToManyField('CGGroup', related_name='users')

    created_chars: 'RELATED_MANAGER_TYPE[CharModel]'
    directly_allowed_chars: 'RELATED_MANAGER_TYPE[CharModel]'
    direct_char_permissions: 'RELATED_MANAGER_TYPE[UserPermissionsForChar]'
    chars: 'RELATED_MANAGER_TYPE[CharModel]'
    char_data_set: 'RELATED_MANAGER_TYPE[CharUsers]'

    def __str__(self) -> str:
        return self.username

    @property
    def is_staff(self) -> bool:
        """
            Used by Django's built-in admin (web-)interface to determine whether the user has access to that interface.

            Note: Is_superuser is used internally by Django's permissions system to override its default permission
            system for model/object-specific permissions.

            The default permission system is designed for model-specific permissions, not for permissions on the object
            level. (There is an interface for the latter, but it requires a lot of tweaking.
            Arguably, it is overengineered for our purpose (due to being too tightly coupled to generic authentication
            backends, of which it allows several simultaneously)
            and tweaking it is more work than implementing a simpler system that works for CharGenNG)

            Since CGUser does not include PermissionsMixin and we actively disable Django's permissions system,
            we do not need to distinguish is_staff and is_superuser.
            The only Django permissions that we use is that only users with is_admin can use Django's admin interface
            and there are no restrictions there.
        """

        return self.is_admin

    @property
    def is_superuser(self) -> bool:
        return self.is_admin

    # noinspection PyUnusedLocal
    def has_perm(self, perm, obj=None) -> bool:
        return self.is_admin

    # noinspection PyUnusedLocal
    def has_module_perms(self, perm, obj=None) -> bool:
        return self.is_admin

class CGGroup(models.Model):
    class Meta:
        default_permissions = ()
    name: str = models.CharField(max_length=150, unique=True, blank=False)

    objects: 'MANAGER_TYPE[CGGroup]'
    users: 'RELATED_MANAGER_TYPE[CGUser]'
    allowed_chars: 'RELATED_MANAGER_TYPE[CharModel]'
    char_permissions: 'RELATED_MANAGER_TYPE[GroupPermissionsForChar]'

    def __str__(self) -> str:
        return self.name


def get_default_group() -> CGGroup:
    """
    :return: the "all users" group that all users are put in by default upon creation.
    """
    all_group, created = CGGroup.objects.get_or_create(pk=1, defaults={'name': 'all users'})
    if created:
        logger.warning('Had to setup CGGroup for all users')
    elif all_group.name != 'all users':
        logger.critical('CGGroup with id 1 does not have the expected name.')
    return all_group


CHAR_NAME_MAX_LENGTH = 80
CV_DESCRIPTION_MAX_LENGTH = 240
MAX_INPUT_LENGTH = 200

class CharModel(models.Model):
    """
    Character stored in database. Note that a character consists of several versions, which are what hold most data.
    Non-versioned data involves only permissions and some display stuff.
    """
    class Meta:
        default_permissions = ()
    name: str = models.CharField(max_length=CHAR_NAME_MAX_LENGTH)
    description: str = models.CharField(max_length=240, blank=True)
    max_version: int = models.PositiveIntegerField(default=1)
    creation_time: datetime = models.DateTimeField(auto_now_add=True)
    last_save: datetime = models.DateTimeField()
    last_change: datetime = models.DateTimeField()
    creator: Optional[CGUser] = models.ForeignKey(CGUser, on_delete=models.SET_NULL, null=True, related_name='created_chars')
    user_level_permissions = models.ManyToManyField(CGUser, through='UserPermissionsForChar', related_name='directly_allowed_chars')
    group_level_permissions = models.ManyToManyField(CGGroup, through='GroupPermissionsForChar', related_name='allowed_chars')
    users = models.ManyToManyField(CGUser, through='CharUsers', related_name='chars', related_query_name='char')

    objects: 'MANAGER_TYPE[CharModel]'
    versions: 'RELATED_MANAGER_TYPE[versions]'  # reverse foreign key
    direct_user_permissions: 'RELATED_MANAGER_TYPE[UserPermissionsForChar]'
    group_permissions: 'RELATED_MANAGER_TYPE[GroupPermissionsForChar]'
    user_data_set: 'RELATED_MANAGER_TYPE[CharUsers]'

    def __str__(self) -> str:
        return str(self.name)



def _error_on_delete():
    logger.error("deleting parent CharVersion")
    return None

class CharVersionModel(models.Model):
    """
    Data stored in the database for a char version. Note that many CharVersionModels belong to a single CharModel
    """

    class Meta:
        get_latest_by = 'creation_time'
        default_permissions = ()

    # Name of the char. This is included in CharVersionModel to allow renames.
    # If empty, we take the owning CharModel's name.
    version_name: str = models.CharField(max_length=CHAR_NAME_MAX_LENGTH, blank=True, default="")

    @property
    def name(self) -> str:
        my_name = self.version_name
        if my_name:
            return str(my_name)
        else:
            return str(self.owner.name)

    # Short description of char Version
    description: str = models.CharField(max_length=CV_DESCRIPTION_MAX_LENGTH, blank=True)
    # Version number is used to construct a short name to refer to versions.
    char_version_number: int = models.PositiveIntegerField()
    # Creation time of this char version. Set automatically.
    creation_time: datetime = models.DateTimeField(auto_now_add=True)
    # Time of last edit. Handled automatically.
    last_changed: datetime = models.DateTimeField(auto_now=True)
    # Incremented every time an edit is made.
    edit_counter: int = models.PositiveIntegerField(default=1)
    # parent version (null for root).
    # We have a pre_delete signal to ensure the tree structure.
    # This is done via a signal to ensure it works on bulk deletes
    parent: 'Optional[CharVersionModel]' = models.ForeignKey('self', on_delete=models.DO_NOTHING, null=True, blank=True, related_name='children', related_query_name='child')
    children: 'MANAGER_TYPE[CharVersionModel]'  # reverse foreign key
    # JSON metadata to initialize the data sources
    data_sources: str = models.TextField(blank=True)
    # Edit mode
    edit_mode: bool = models.BooleanField(default=False)
    # owning char
    owner: CharModel = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='versions', related_query_name='char_version')

    def __str__(self) -> str:
        if self.edit_mode:
            return self.name + " V" + str(self.char_version_number) + "+"
        else:
            return self.name + " V" + str(self.char_version_number)


# permissions set on a user level. Do not use directly.
class UserPermissionsForChar(models.Model):
    class Meta:
        # default_permissions is for Django's admin interface, unrelated to the permissions modeled by UserPermissions.
        default_permissions = ()
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


class GroupPermissionsForChar(models.Model):
    class Meta:
        # default_permissions is for Django's admin interface, unrelated to the permissions modeled by GroupPermissions.
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['char', 'group'], name='m2mgroupperms'),
            models.CheckConstraint(check=models.Q(may_read__gte=models.F('may_write')), name='group_write_implies_read'),
        ]
        indexes = [models.Index(fields=['char', 'group'])]
    char: str = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='group_permissions')
    group: CGGroup = models.ForeignKey(CGGroup, on_delete=models.CASCADE, related_name='char_permissions')
    may_read: bool = models.BooleanField(default=True)
    may_write: bool = models.BooleanField(default=True)

    objects: 'MANAGER_TYPE[GroupPermissionsForChar]'
    affected_char_permissions: 'MANAGER_TYPE[CharUsers]'

class CharUsers(models.Model):
    """
        Entries for every (char, user)-pair for which user has at least some permissions for char.
        This includes indirect permissions through group membership and is synchronized with user-level and group-level
        permissions. Also stores other relevant data for the pair: at the moment, the last opened char version.
    """
    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['char', 'user'], name='m2mcharuser'),
            models.CheckConstraint(check=models.Q(read_permission__gte=models.F('write_permission')), name='write_implies_read'),
        ]
        indexes = [models.Index(fields=['char', 'user'])]
    char: str = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='user_data_set')
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
                char_user = CharUsers(char=char, user=user, opened_version=None, true_read_permissions=False, true_write_permissions=False, group_reason=None)
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
