from enum import IntEnum
from django.db.models import IntegerChoices

class EditModes(IntEnum):
    NORMAL = 0
    EDIT_DATA_OVERWRITE = 1
    EDIT_DATA_NEW = 2
    EDIT_CONFIG_OVERWRITE = 3
    EDIT_CONFIG_NEW = 4

    def __bool__(self):
        return self is not EditModes.NORMAL

    def as_int(self):
        return int(self)

    def is_edit_data(self):
        return (self is EditModes.EDIT_DATA_OVERWRITE) or (self is EditModes.EDIT_DATA_NEW)

    def is_edit_config(self):
        return (self is EditModes.EDIT_CONFIG_OVERWRITE) or (self is EditModes.EDIT_CONFIG_NEW)
