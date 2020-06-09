"""
This module defines the database models that are responsible for CharGenNG.
Notably, we define some models for user authentication and for actual chars.
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
import logging
from django.db import transaction, IntegrityError
from django.core.exceptions import ObjectDoesNotExist
from typing import Optional, TypeVar, Generic, Iterator, Iterable, Union
from datetime import datetime, timezone

# Only used for static type checking and to ensure my IDE's autocompletion works.
# MANAGER_TYPE[ModelClass] is the type of ModelClass.objects.all() / ModelClass.objects
# (we ignore the differences here)
# django automatically adds an 'object' class attribute of this type to our database model classes.
_Z = TypeVar('_Z')
class MANAGER_TYPE(Generic[_Z], models.QuerySet, models.Manager):
    def __iter__(self) -> Iterator[_Z]: ...


CHAR_NAME_MAX_LENGTH = 80  # max length of char name
CHAR_DESCRIPTION_MAX_LENGTH = 240  # max length of char descriptions
CV_DESCRIPTION_MAX_LENGTH = 240  # max length of char version descriptions
MAX_INPUT_LENGTH = 200  # max length of (short) text field inputs
KEY_MAX_LENGTH = 240  # max length of dict keys (for chars)
CG_USERNAME_MAX_LENGTH = 40 # max length of usernames


# When setting a foreign key attribute in model A to model B, django automatically adds an a_set attribute to B.
# (name can be customized and usually is). Setting a type hint
# a_set : RELATED_MANAGER_TYPE[A]
# to B makes the static type checker a little less grumpy.
class RELATED_MANAGER_TYPE(MANAGER_TYPE[_Z]):
    # Note that such Manager classes are internally dynamically constructed from inner classes by Django, so we can't
    # import and derive from it here; we rather set the methods manually...
    def add(self, *obs, bulk=True, through_defaults=None): ...
    # need to add some more functions that are specific to such related managers.

class MyMeta:
    """
    default metaclass for our database models.
    default_permissions = () basically disables the permission checking done by Django's pre-built admin interface.
    This is completely unrelated to the CharModel-level permissions we manage for our users.
    We do not use django's system, because Django only allows (without lots of work) to set permissions on a database-
    table level, not on individual database entries. (=> a user can edit either all chars or none if using Django's
    default system). Django's admin interface is only used by the admin, for whom all permissions are ignored anyway.
    """
    default_permissions = ()


logger = logging.getLogger('chargen.database')
user_logger = logging.getLogger('chargen.database.users')
char_logger = logging.getLogger('chargen.database.char')  # for logging char-based management

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
    objects: 'MANAGER_TYPE[CGUser]' = CGUserManager()  # object manager. We can't use the default one
    is_active: bool = models.BooleanField(default=True)  # internally expected by Django.
    is_admin: bool = models.BooleanField(default=False)  # for the admin user
    email: str = models.EmailField(verbose_name='email address', max_length=255)
    groups: 'RELATED_MANAGER_TYPE[CGGroup]' = models.ManyToManyField('CGGroup', related_name='users')

    # backlinks from other models that refer to CGUser go here:
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
        """Permissions override by Django's admin system"""
        return self.is_admin

    # noinspection PyUnusedLocal
    def has_perm(self, perm, obj=None) -> bool:
        return self.is_admin

    # noinspection PyUnusedLocal
    def has_module_perms(self, perm, obj=None) -> bool:
        return self.is_admin

    def may_read_char(self, *, char: 'Union[CharModel, CharVersionModel]') -> bool:
        """Does this user have read access to char"""
        return CharUsers.user_may_read(user=self, char=char)

    def may_write_char(self, *, char: 'Union[CharModel, CharVersionModel]') -> bool:
        """Does this user have read/write access to char"""
        return CharUsers.user_may_write(user=self, char=char)


class CGGroup(models.Model):
    class Meta(MyMeta):
        pass
    name: str = models.CharField(max_length=150, unique=True, blank=False)

    objects: 'MANAGER_TYPE[CGGroup]'
    users: 'RELATED_MANAGER_TYPE[CGUser]'
    allowed_chars: 'RELATED_MANAGER_TYPE[CharModel]'
    char_permissions: 'RELATED_MANAGER_TYPE[GroupPermissionsForChar]'

    def __str__(self) -> str:
        return self.name

    @classmethod
    def create_group(cls, name, *, initial_users: Iterable[CGUser]):
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
        logger.warning('Had to setup CGGroup for all users')
    elif all_group.name != 'all users':
        logger.critical('CGGroup with id 1 does not have the expected name.')
    return all_group

class CharModel(models.Model):
    """
    Character stored in database. Note that a character consists of several versions, which are what hold most data.
    Non-versioned data involves only permissions and some display stuff.
    (Notably, we store data here that we want to display on a webpage where the user selects a char she wants to view)
    """
    class Meta(MyMeta):
        pass
    name: str = models.CharField(max_length=CHAR_NAME_MAX_LENGTH)  # name of the char (may be changed in a version)
    description: str = models.CharField(max_length=CHAR_DESCRIPTION_MAX_LENGTH, blank=True)  # short description
    max_version: int = models.PositiveIntegerField(default=1)  # The next char version created gets this number attached to it as a (purely informational) version number.
    creation_time: datetime = models.DateTimeField(auto_now_add=True)  # time of creation. Read-only and managed automatically.
    # The difference between last_change and last_save is that edits in chars opened for editing get changed immediately
    # upon user input (via Javascript), whereas last_save involves actually manually saving (which is implemented as an
    # change in CharVersionsModels rather than a change in DictEntries)
    last_save: datetime = models.DateTimeField()  # time of last change of char.
    last_change: datetime = models.DateTimeField()  # time of last SAVE of char. CharVersions should change that upon change.
    creator: Optional[CGUser] = models.ForeignKey(CGUser, on_delete=models.SET_NULL, null=True, related_name='created_chars')
    user_level_permissions = models.ManyToManyField(CGUser, through='UserPermissionsForChar', related_name='directly_allowed_chars')
    group_level_permissions = models.ManyToManyField(CGGroup, through='GroupPermissionsForChar', related_name='allowed_chars')
    users = models.ManyToManyField(CGUser, through='CharUsers', related_name='chars', related_query_name='char')

    objects: 'MANAGER_TYPE[CharModel]'
    versions: 'RELATED_MANAGER_TYPE[versions]'
    direct_user_permissions: 'RELATED_MANAGER_TYPE[UserPermissionsForChar]'
    group_permissions: 'RELATED_MANAGER_TYPE[GroupPermissionsForChar]'
    user_data_set: 'RELATED_MANAGER_TYPE[CharUsers]'

    def __str__(self) -> str:
        return str(self.name)

    @classmethod
    def create_char(cls, name: str, creator: CGUser, *, description: str = "") -> 'CharModel':
        """
        Creates a new char with the given name and description.
        The creator is recorded as the creator and given read/write permissions.
        You will need to create an initial char version by char.make_char_version(...)
        :return: char
        """
        current_time: datetime = datetime.now(timezone.utc)
        new_char = cls(name=name, description=description, max_version=1, last_save=current_time,
                       last_change=current_time, creator=creator)
        with transaction.atomic():
            new_char.save()  # need to save at this point, because recomputing permissions may reload from db.
            UserPermissionsForChar.objects.create(char=new_char, user=creator)
        return new_char

    def create_char_version(self, *args, **kwargs) -> 'CharVersionModel':
        """
        Creates a new char version for this char (shortcut for a method of CharModel)
        Refer to CharVersionModel.create_char_version for details
        """
        if 'owner' in kwargs:
            raise ValueError("Use class method CharVersionModel.create_char_version to change owner")
        return CharVersionModel.create_char_version(*args, **kwargs, owner=self)

    def may_be_read_by(self, *, user: CGUser) -> bool:
        """
        shorthand to check read permissions.
        """
        return CharUsers.user_may_read(char=self, user=user)

    def may_be_written_by(self, *, user: CGUser) -> bool:
        """
        shorthand to check read/write permission.
        """
        return CharUsers.user_may_write(char=self, user=user)


class CharVersionModel(models.Model):
    """
    Data stored in the database for a char version. Note that many CharVersionModels belong to a single CharModel
    """

    class Meta(MyMeta):
        get_latest_by = 'creation_time'

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
    # Creation time of this char version. Set automatically. Read-only.
    creation_time: datetime = models.DateTimeField(auto_now_add=True)
    # Time of last edit. Updated automatically by Django every time we save to the database.
    last_changed: datetime = models.DateTimeField(auto_now=True)
    # Should be incremented every time an edit is made. This may be useful to handle some concurrency issues more gracefully.
    edit_counter: int = models.PositiveIntegerField(default=1)
    # parent version (null for root).
    # We have a pre_delete signal to ensure the tree structure.
    # This is done via a signal to ensure it works on bulk deletes
    parent: 'Optional[CharVersionModel]' = models.ForeignKey('self', on_delete=models.DO_NOTHING, null=True, blank=True,
                                                             related_name='children', related_query_name='child')
    children: 'RELATED_MANAGER_TYPE[CharVersionModel]'  # reverse foreign key
    # JSON metadata to initialize the data sources
    data_sources: str = models.TextField(blank=True)
    # Edit mode
    edit_mode: bool = models.BooleanField(default=False)
    # owning char
    owner: CharModel = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='versions', related_query_name='char_version')

    objects: 'MANAGER_TYPE[CharVersionModel]'

    def __str__(self) -> str:
        if self.edit_mode:
            return self.name + " V" + str(self.char_version_number) + "+"
        else:
            return self.name + " V" + str(self.char_version_number)

    @classmethod
    def create_char_version(cls, *, version_name: str = None, description: str = None, edit_mode: bool = None,
                            parent: 'Optional[CharVersionModel]' = None, data_sources=None, owner: CharModel = None):
        """
        Creates a new char version. Parameters are taken from parent char version unless overridden by arguments
        to create_char_version. Note that both owner and parent need to be saved in the db.
        If parent is None, owner needs to be set, this creates a root char version.
        Note that this function may change owner / parent.owner
        """
        changed_owner = False
        if parent:
            assert isinstance(parent, cls)
            new_version: CharVersionModel = cls.objects.get(pk=parent.pk)
            new_version.pk = None
            if version_name is not None:  # but may be ""
                new_version.version_name = version_name
            if data_sources is not None:  # but may be ""
                new_version.data_sources = data_sources
            if edit_mode is not None:  # but may be False
                new_version.edit_mode = edit_mode
            if description is not None:  # but may be ""
                new_version.description = description
            if new_version.edit_mode and parent.edit_mode:
                raise ValueError("Can not create an edit char version from an edit char version")
            new_version.edit_counter += 1
            new_version.last_changed = datetime.now(timezone.utc)
            if owner and new_version.owner != owner:  # new char from previous version
                if new_version.edit_mode or parent.edit_mode:
                    raise ValueError("Creating an initial char version for a new char from an old char version not possible in edit mode")
                new_version.parent = None
                new_version.owner = owner
                new_version.char_version_number = owner.max_version
                owner.max_version += 1  # not yet saved to db.
                changed_owner = True
            else:  # previous owner (the common case)
                new_version.parent = parent
                if not new_version.edit_mode:
                    new_version.char_version_number = owner.max_version
                    new_version.owner.max_version += 1
                    changed_owner = True
        else:  # No parent, so we create a brand new char version for the char given by owner
            if not owner:
                raise ValueError("Either parent or owner must be provided to create a char version")
            version_name = version_name or ""
            data_sources = data_sources or ""
            description = description or ""
            if edit_mode:
                raise ValueError("Editing only allowed based on an existing char")

            new_version: CharVersionModel = CharVersionModel(version_name=version_name, data_sources=data_sources,
                                                             char_version_number=owner.max_version, last_changed=datetime.now(timezone.utc),
                                                             description=description, edit_counter=1, parent=None,
                                                             edit_mode=False, owner=owner)
            new_version.owner.max_version += 1
            changed_owner = True
        with transaction.atomic():
            new_version.save()
            if changed_owner:
                new_version.owner.save()
        return new_version

    def may_be_read_by(self, *, user: CGUser) -> bool:
        return CharUsers.user_may_read(char=self, user=user)

    def may_be_written_by(self, *, user: CGUser) -> bool:
        return CharUsers.user_may_write(char=self, user=user)


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

class DictEntry(models.Model):
    class Meta(MyMeta):
        abstract = True
        constraints = [
            models.UniqueConstraint(fields=['char_version', 'key'], name="unique_key_%(class)s"),
            models.CheckConstraint(check=~models.Q(value=""), name="non_empty_values_%(class)s"),
        ]
        indexes = [
            models.Index(fields=['char_version', 'key'], name="lookup_index_%(class)s"),
        ]

    char_version: CharVersionModel = models.ForeignKey(CharVersionModel, on_delete=models.CASCADE, null=False,
                                                       related_name="%(class)s_set")
    key: str = models.CharField(max_length=KEY_MAX_LENGTH, null=False, blank=False)
    value: str

    objects: 'MANAGER_TYPE[DictEntry]'

class ShortDictEntry(DictEntry):
    # Blank=True is validation-related. While entering blank values is allowed (it deletes the entry), this needs to
    # be handled manually. The only place where blank matters is the admin interface, which does not know about
    # our custom logic. So we set blank to False.
    value: str = models.CharField(max_length=MAX_INPUT_LENGTH, blank=False, null=False)

class LongDictEntry(DictEntry):
    value: str = models.TextField(blank=False, null=False)
