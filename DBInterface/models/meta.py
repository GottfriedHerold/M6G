from __future__ import annotations
from typing import TypeVar, Generic, Iterator, Final

from django.db import models


CHAR_NAME_MAX_LENGTH: Final = 80  # max length of char name
CHAR_DESCRIPTION_MAX_LENGTH: Final = 240  # max length of char descriptions
CV_DESCRIPTION_MAX_LENGTH: Final = 240  # max length of char version descriptions
MAX_INPUT_LENGTH: Final = 200  # max length of (short) text field inputs
KEY_MAX_LENGTH: Final = 240  # max length of dict keys (for chars)
CG_USERNAME_MAX_LENGTH: Final = 40  # max length of usernames
MAX_GROUP_NAME_LENGTH: Final = 150

# Only used for static type checking and to ensure Pycharm's autocompletion works.
# MANAGER_TYPE[ModelClass] is the type of ModelClass.objects.all() / ModelClass.objects
# (we ignore the differences here)
# django automatically adds an 'object' class attribute of this type to our database model classes.
_Z = TypeVar('_Z')
class MANAGER_TYPE(Generic[_Z], models.QuerySet, models.Manager):
    def __iter__(self) -> Iterator[_Z]: ...

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
