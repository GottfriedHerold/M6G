from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group
import logging

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

CHAR_NAME_MAX_LENGTH = 80
CV_DESCRIPTION_MAX_LENGTH = 240
MAX_INPUT_LENGTH = 200
logger = logging.getLogger('chargen.database')
user_logger = logging.getLogger('chargen.database.users')

def get_default_group():
    all_group, created = Group.objects.get_or_create(pk=1, defaults={'name': 'all users'})
    if created:
        logger.warning('Had to setup group for all users')
    elif all_group.name != 'all users':
        logger.critical('Group with id 1 does not have the expected name.')
    return all_group

def _error_on_delete():
    logger.error("deleting parent CharVersion")
    return None


class CharVersionModel(models.Model):
    """
    Data stored in the database for a char version. Note that there are Many-to-one relationships from Char
    """
    # Name of the char. This is included in CharVersionModel to allow renames.
    # If empty, we take the owning CharModel's name.
    version_name = models.CharField(max_length=CHAR_NAME_MAX_LENGTH, blank=True, default="")
    owner__name: models.CharField

    class Meta:
        get_latest_by = 'creation_time'
        default_permissions = ()


    @property
    def name(self) -> str:
        my_name = self.version_name
        if my_name:
            return str(my_name)
        else:
            return str(self.owner__name)

    # Short description of char Version
    description = models.CharField(max_length=CV_DESCRIPTION_MAX_LENGTH, blank=True)
    # Version number is used to construct a short name to refer to versions.
    char_version_number = models.PositiveIntegerField()
    # Creation time of this char version. Set automatically.
    creation_time = models.DateTimeField(auto_now_add=True)
    # Time of last edit. Handled automatically.
    last_changed = models.DateTimeField(auto_now=True)
    # Incremented every time an edit is made.
    edit_counter = models.PositiveIntegerField(default=1)
    # parent version
    parent = models.ForeignKey('self', on_delete=models.SET(_error_on_delete), null=True, related_name='children', related_query_name='child')
    # JSON metadata to initialize the data sources
    meta_sources = models.TextField()
    # Edit mode
    edit_mode = models.BooleanField(default=False)
    # owning char
    owner = models.ForeignKey('CharModel', on_delete=models.CASCADE, related_name='versions', related_query_name='char_version')

    def __str__(self):
        if self.edit_mode:
            return self.name + " V" + str(self.char_version_number) + "+"
        else:
            return self.name + " V" + str(self.char_version_number)

class CharModel(models.Model):
    class Meta:
        default_permissions = ()
    name = models.CharField(max_length=CHAR_NAME_MAX_LENGTH)
    description = models.CharField(max_length=240, blank=True)
    max_version = models.PositiveIntegerField(default=1)
    creation_time = models.DateTimeField(auto_now_add=True)
    last_save = models.DateTimeField()
    last_change = models.DateTimeField()
    creator = models.ForeignKey('CGUser', on_delete=models.SET_NULL, null=True, related_name='created_chars')
    user_permissions = models.ManyToManyField('CGUser', through='UserPermissions', related_name='allowed_chars')
    group_permissions = models.ManyToManyField(Group, through='GroupPermissions', related_name='allowed_groups')
    users = models.ManyToManyField('CGUser', through='CharUsers', related_name='users', related_query_name='user')

class UserPermissions(models.Model):
    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['char', 'user'], name='m2muserperms')]
        indexes = [models.Index(fields=['char', 'user'])]
    char = models.ForeignKey(CharModel, on_delete=models.CASCADE)
    user = models.ForeignKey('CGUser', on_delete=models.CASCADE)
    may_read = models.BooleanField(default=True)
    may_write = models.BooleanField(default=True)
    # TODO: save

class GroupPermissions(models.Model):
    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['char', 'group'], name='m2mgroupperms')]
        indexes = [models.Index(fields=['char', 'group'])]
    char = models.ForeignKey(CharModel, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    may_read = models.BooleanField(default=True)
    may_write = models.BooleanField(default=True)
    # TODO: save

class CharUsers(models.Model):
    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['char', 'user'], name='m2mcharuser')]
        indexes = [models.Index(fields=['char', 'user'])]
    char = models.ForeignKey(CharModel, on_delete=models.CASCADE)
    user = models.ForeignKey('CGUser', on_delete=models.CASCADE)
    opened_version = models.ForeignKey(CharVersionModel, on_delete=models.SET_NULL, null=True, related_name='+')
    read_permission = models.BooleanField()
    write_permission = models.BooleanField()


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
    username = models.CharField(max_length=40, unique=True)
    USERNAME_FIELD = 'username'  # database field that is used as username in the login.
    REQUIRED_FIELDS = ['email']  # list of additional mandatory fields queried in the "manage.py createsuperuser" script.
    objects = CGUserManager()  # object manager. We can't use the default one
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    email = models.EmailField(verbose_name='email address', max_length=255)
    groups = models.ManyToManyField(Group)

    def __str__(self):
        return self.username

    @property
    def is_staff(self):
        """
            Used by Django's built-in Admin (web-)interface to determine whether the user has access to that interface.
            Note that is_superuser is used internally by Django to override its default permission system for model/object-
            specific permissions. These are, in general, different things, hence Django distinguishes staff and admin.
            Since CGUser does not include PermissionsMixin and we actively disable Django's permissions system,
            we do not need to make that distinction.
            The only Django permissions that we use is that only the admin can use the admin interface and there
            are no restrictions for the admin there.
        """

        return self.is_admin

    @property
    def is_superuser(self):
        return self.is_admin

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, perm, obj=None):
        return self.is_admin
