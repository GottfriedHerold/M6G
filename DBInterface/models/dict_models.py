from django.db import models

from .meta import MyMeta, KEY_MAX_LENGTH, MAX_INPUT_LENGTH
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
    # be handled manually. The only place where blank matters is the admin interface, which does not know about
    # our custom logic. So we set blank to False.
    value: str = models.CharField(max_length=MAX_INPUT_LENGTH, blank=False, null=False)


class LongDictEntry(DictEntry):
    value: str = models.TextField(blank=False, null=False)