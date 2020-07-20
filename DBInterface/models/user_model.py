from __future__ import annotations
import logging
from typing import Iterable, TYPE_CHECKING, Union

from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.db import models, transaction, IntegrityError
from django.conf import settings

# from .models import CharUsers
from .meta import MyMeta, CG_USERNAME_MAX_LENGTH, RELATED_MANAGER_TYPE, MANAGER_TYPE, MAX_GROUP_NAME_LENGTH
if TYPE_CHECKING:
    from . import CharModel, CharVersionModel, CharUsers
    from .permission_models import UserPermissionsForChar, GroupPermissionsForChar

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
# with the parent class providing hardly any functionality. Also, it's too tightly integrated to Authentication Backends).
# The following together with forms in admin.py is adapted from an example in the docs.
class CGUserManager(BaseUserManager):
    """
    Manager class for CGUser (our user class).
    """
    def create_user(self, username, email, password=None):
        """
        Creates a standard (non-admin) user with given username, email and password.
        Adds the newly created user to the "all users" group
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
        """
        creates a superuser. This is required to run manage.py createsuperuser
        """
        user = self.create_user(username=username, email=email, password=password)
        user.is_admin = True
        user.save(using=self._db)
        if settings.TESTING_MODE:
            user_logger.info('Turned user into superuser with username %s', username)
        else:
            user_logger.critical('Turned user into superuser with username %s', username)
        return user


class CGUser(AbstractBaseUser):
    """
    User class.
    """
    class Meta(MyMeta):
        constraints = [
            models.CheckConstraint(check=~models.Q(username__iexact="guest"), name='no_guest_user'),  # guest as username would cause confusion
        ]
    username: str = models.CharField(max_length=CG_USERNAME_MAX_LENGTH, unique=True)
    USERNAME_FIELD = 'username'  # database field that is used as username in the login.
    REQUIRED_FIELDS = ['email']  # list of additional mandatory fields queried in the "manage.py createsuperuser" script.
    objects: MANAGER_TYPE[CGUser] = CGUserManager()  # object manager. We can't use the default one
    is_active: bool = models.BooleanField(default=True)  # internally expected by Django.
    is_admin: bool = models.BooleanField(default=False)  # for the admin user
    email: str = models.EmailField(verbose_name='email address', max_length=255)
    groups: RELATED_MANAGER_TYPE[CGGroup] = models.ManyToManyField('CGGroup', related_name='users')

    # backlinks from other models that refer to CGUser go here:
    created_chars: RELATED_MANAGER_TYPE[CharModel]
    directly_allowed_chars: RELATED_MANAGER_TYPE[CharModel]
    direct_char_permissions: RELATED_MANAGER_TYPE[UserPermissionsForChar]
    chars: RELATED_MANAGER_TYPE[CharModel]
    char_data_set: RELATED_MANAGER_TYPE[CharUsers]

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
        """Permissions override by Django's admin system"""
        return self.is_admin

    # noinspection PyUnusedLocal
    def has_perm(self, perm, obj=None) -> bool:
        return self.is_admin

    # noinspection PyUnusedLocal
    def has_module_perms(self, perm, obj=None) -> bool:
        return self.is_admin

    def may_read_char(self, *, char: Union[CharModel, CharVersionModel]) -> bool:
        """Does this user have read access to char"""
        from .permission_models import CharUsers
        return CharUsers.user_may_read(user=self, char=char)

    def may_write_char(self, *, char: Union[CharModel, CharVersionModel]) -> bool:
        """Does this user have read/write access to char"""
        from .permission_models import CharUsers
        return CharUsers.user_may_write(user=self, char=char)


class CGGroup(models.Model):
    class Meta(MyMeta):
        pass
    name: str = models.CharField(max_length=MAX_GROUP_NAME_LENGTH, unique=True, blank=False)

    objects: MANAGER_TYPE[CGGroup]
    users: RELATED_MANAGER_TYPE[CGUser]
    allowed_chars: RELATED_MANAGER_TYPE[CharModel]
    char_permissions: RELATED_MANAGER_TYPE[GroupPermissionsForChar]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def create_group(cls, name, *, initial_users: Iterable[CGUser]) -> CGGroup:
        with transaction.atomic():
            try:
                new_group: CGGroup = cls.objects.create(name=name)
            except IntegrityError:
                raise ValueError("Group with name %s already exists" % name)
            if initial_users:
                new_group.users.add(*initial_users)
        return new_group


def get_default_group() -> CGGroup:
    """
    :return: the "all users" group that all users are put in by default upon creation.
    """
    all_group, created = CGGroup.objects.get_or_create(pk=1, defaults={'name': 'all users'})
    if created:
        if settings.TESTING_MODE is False:
            logger.warning('Had to setup CGGroup for all users')
        else:
            logger.debug('Had to setup CGGroup for all users')
    elif all_group.name != 'all users':
        logger.critical('CGGroup with id 1 does not have the expected name.')
    return all_group
