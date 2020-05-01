from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group

# Create your models here.

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

class CGUser(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=40, unique=True)
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']
    objects = CGUserManager()
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
