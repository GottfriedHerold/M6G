from __future__ import annotations
from enum import IntEnum
# from django.db.models import IntegerChoices
from typing import Final

class EditModes(IntEnum):
    NORMAL = 0
    EDIT_DATA_OVERWRITE = 1
    EDIT_DATA_NEW = 2
    EDIT_CONFIG_OVERWRITE = 3
    EDIT_CONFIG_NEW = 4
    EDIT_ALL_OVERWRITE = 5
    EDIT_ALL_NEW = 6

    def __bool__(self, /) -> bool:
        return self is not EditModes.NORMAL

    def as_int(self, /) -> int:
        return int(self)

    def may_edit_data(self, /) -> bool:
        return (self is EditModes.EDIT_DATA_OVERWRITE) or (self is EditModes.EDIT_DATA_NEW) or (self is EditModes.EDIT_ALL_NEW) or (self is EditModes.EDIT_ALL_OVERWRITE)

    def may_edit_config(self, /) -> bool:
        return (self is EditModes.EDIT_CONFIG_OVERWRITE) or (self is EditModes.EDIT_CONFIG_NEW) or (self is EditModes.EDIT_ALL_NEW) or (self is EditModes.EDIT_ALL_OVERWRITE)

    def is_overwriter(self, /) -> bool:
        return (self is EditModes.EDIT_DATA_OVERWRITE) or (self is EditModes.EDIT_CONFIG_OVERWRITE) or (self is EditModes.EDIT_ALL_OVERWRITE)

    @staticmethod
    def allowed_reference_targets():
        return ALLOWED_REFERENCE_TARGETS


ALLOWED_REFERENCE_TARGETS: Final = [EditModes.NORMAL]

# For Django
EditModesChoices: Final = list(map(lambda x: (x.value, x.name), EditModes))
