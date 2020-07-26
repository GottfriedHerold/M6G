"""
Character versions can be in some different modes, called EditModes, with regards to what operations are allowed on
them. Because evaluation is fully server-sided, edits in the UI need to be immediately saved in the db.
As a result, we want to distinguish normal versions (read-only, essentially) and versions that are in the process of being
edited in order to provide "undo" possibilities. UI edits can only go into editable versions.
Saving is then just a matter of essentially renaming, optionally copying and/or removing the old version.
Another issue is reference validity and caching: If a char version refers to another, the target should be read-only and
NOT be overwritten (Remember that overwriting essentially deletes).
For now, we distinguish in edit modes between editing data and editing the config. Changing requires switching edit mode,
which forces changing the database primary key. We also distinguish edits mode into whether saving should (by default)
override a given previous non-editable version. This is mostly a convenience feature.
Note that the design strongly encourages (and to some extent forces) the user to create backup copies before performing
certain changes. In particular, using the learning mode requires a charversion to diff against a previous version,
making a non-editable save of the previous version neccessary (that can later be removed if needed).
"""

from __future__ import annotations
from enum import IntEnum
# from django.db.models import IntegerChoices
from typing import Final


class EditModes(IntEnum):
    """
    List of all possible edit modes. We have an explict list here rather than flags that can be arbitrarily combined.
    """
    # We make up the explict list of edit modes from flags in order to simplify the queries (e.g. is_overwriter) below.
    # Overwrite = 1  version with this flag refer to some other target version and need to be editable.
    #                Upon "saving" in the UI, by default, we overwrite, i.e. remove that target.
    #                Otherwise, "saving" in the UI just drops editability, thereby creating a new non-editable
    #                backup version.
    # Edit_data = 2   # Can edit data of the char.
    # Edit_Config = 4  # Can edit metadata of the char.
    NORMAL = 0  # Version stored in db can can not be modified, but can be deleted (which is how "overwriting" works)
    EDIT_DATA_OVERWRITE = 3
    EDIT_DATA_NEW = 2
    EDIT_CONFIG_OVERWRITE = 5
    EDIT_CONFIG_NEW = 4
    EDIT_ALL_OVERWRITE = 7
    EDIT_ALL_NEW = 6

    def __bool__(self, /) -> bool:
        return self is not EditModes.NORMAL

    def as_int(self, /) -> int:
        return int(self)

    def may_edit_data(self, /) -> bool:
        return bool(self.value & 0x2)

    def may_edit_config(self, /) -> bool:
        return bool(self.value & 0x4)

    def is_overwriter(self, /) -> bool:
        return bool(self.value & 0x1)

    @staticmethod
    def allowed_reference_targets():
        return ALLOWED_REFERENCE_TARGETS


#  EditModes.allowed_reference_targets() == ALLOWED_REFERENCE_TARGETS is the list of all EditModes for which we
#  allow the char version to be possibly a target of a reference by another char version.
#  Basically, we do not want a referred char to be modified / overwritten / deleted.
#  The target's edit mode is not the only restriction:
#  deleting a char that is the target of a reference is actually guarded against by the DB. This includes the
#  target of char with Edit_*_OVERWRITE, so targets of EDIT_*_OVERWRITE must not be targets by anything else.
#  We might consider adding an edit mode for being an EDIT_*_OVERWRITE target.
ALLOWED_REFERENCE_TARGETS: Final = [EditModes.NORMAL]


# For Django
EditModesChoices: Final = list(map(lambda x: (x.value, x.name), EditModes))
