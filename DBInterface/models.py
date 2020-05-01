from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group

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
        return user

    def create_superuser(self, username, email, password=None):
        user = self.create_user(username=username, email=email, password=password)
        user.is_admin = True
        user.save(using=self._db)
        return user

# Note: The PermissionsMixin may eventually be removed...
class CGUser(AbstractBaseUser, PermissionsMixin):
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
        """

        return self.is_admin

    @property
    def is_superuser(self):
        return self.is_admin
