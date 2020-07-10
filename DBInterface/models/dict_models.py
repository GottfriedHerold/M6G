from collections import abc

from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from .meta import MyMeta, KEY_MAX_LENGTH, MAX_INPUT_LENGTH, MANAGER_TYPE
from .char_models import CharVersionModel

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

    @classmethod
    def as_dict_for(cls, char_version: CharVersionModel):
        return SimpleDBToDict(char_version_model=char_version, manager=cls.objects)

    @classmethod
    def copy_between_charversions(cls, *, source: CharVersionModel, target: CharVersionModel):
        """
        Copies entries from source char version to target charversion. target charversion must not have any entries.
        """
        if cls.objects.filter(char_version=target).exists():
            raise ValueError("Target charversion dict is not empty")
        old = cls.objects.filter(char_version=source)
        for entry in old:
            entry.pk = None
            entry.char_version = target
        cls.objects.bulk_create(old)


class ShortDictEntry(DictEntry):
    # Blank=True is validation-related. While entering blank values is allowed (it deletes the entry), this needs to
    # be handled manually before even handed to this class.
    # The only place where blank matters is the admin interface, which does not know about our custom logic.
    # So we set blank to False to make it harder for the admin interface to mess things up.
    value: str = models.CharField(max_length=MAX_INPUT_LENGTH, blank=False, null=False)


class LongDictEntry(DictEntry):
    value: str = models.TextField(blank=False, null=False)


class SimpleDBToDict(abc.MutableMapping):
    """
    Wrapper that allows to treat models.DictEntry (and derived types) for a specific CharVersion like a dictionary.

    Usage: SimpleDBToDict(manager, char version). Manager will typically be models.DictEntry.objects
    Can then be used to create a DataSource based on it. This is not very optimized, but will do for now.
    Eventually, it will be more efficient to directly write a DB-based DataSource without an intermediate dict-wrapper.
    """

    manager: MANAGER_TYPE[DictEntry]
    char_version_model: CharVersionModel
    main_manager: MANAGER_TYPE[DictEntry]

    def __init__(self, *, manager: MANAGER_TYPE[DictEntry], char_version_model: CharVersionModel):
        self.char_version_model = char_version_model
        self.main_manager = manager
        self.manager = manager.filter(char_version=self.char_version_model)

    def __getitem__(self, item: str) -> str:
        try:
            return self.manager.get(key=item).value
        except ObjectDoesNotExist:
            raise KeyError

    def __setitem__(self, key: str, value: str):
        self.main_manager.update_or_create(defaults={'value': value}, key=key, char_version=self.char_version_model)

    def __delitem__(self, key: str):
        f = self.manager.filter(key=key)
        if not f.exists():
            raise KeyError(key)
        f.delete()

    def __contains__(self, item: str) -> bool:
        return self.manager.filter(key=item).exists()

    def __len__(self):
        return self.manager.all().count()

    # NOTE: The resulting items() dictview is fairly inefficient.
    def __iter__(self):
        return map(lambda x: x.key, iter(self.manager.all()))