from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, List
import logging
import copy

from django.db import models, transaction, IntegrityError

# from . import CharVersionModel
from .user_model import CGUser, CGGroup
from .meta import MyMeta, CHAR_NAME_MAX_LENGTH, CHAR_DESCRIPTION_MAX_LENGTH, CV_DESCRIPTION_MAX_LENGTH, RELATED_MANAGER_TYPE, MANAGER_TYPE
from CharVersionConfig import EditModes, EditModesChoices, ALLOWED_REFERENCE_TARGETS, CVConfig, PythonConfigRecipe

if TYPE_CHECKING:
    from .permission_models import UserPermissionsForChar, GroupPermissionsForChar, CharUsers

char_logger = logging.getLogger('chargen.database.char')  # for logging char-based management


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
    last_save: datetime = models.DateTimeField()  # time of last save of char. (corresponds to a change wrt existence of CharVersion models)
    last_change: datetime = models.DateTimeField()  # time of last change of char. CharVersions should change that upon change.
    creator: Optional[CGUser] = models.ForeignKey(CGUser, on_delete=models.SET_NULL, null=True, related_name='created_chars')
    user_level_permissions = models.ManyToManyField(CGUser, through='UserPermissionsForChar', related_name='directly_allowed_chars')
    group_level_permissions = models.ManyToManyField(CGGroup, through='GroupPermissionsForChar', related_name='allowed_chars')
    users = models.ManyToManyField(CGUser, through='CharUsers', related_name='chars', related_query_name='char')

    objects: MANAGER_TYPE[CharModel]
    versions: RELATED_MANAGER_TYPE[versions]
    direct_user_permissions: RELATED_MANAGER_TYPE[UserPermissionsForChar]
    group_permissions: RELATED_MANAGER_TYPE[GroupPermissionsForChar]
    user_data_set: RELATED_MANAGER_TYPE[CharUsers]

    def __str__(self) -> str:
        return str(self.name)

    @classmethod
    def create_char(cls, name: str, creator: CGUser, *, description: str = "") -> CharModel:
        """
        Creates a new char with the given name and description.
        The creator is recorded as the creator and given read/write permissions.
        You will need to create an initial char version by char.create_root_char_version(...)
        :return: char
        """
        current_time: datetime = datetime.now(timezone.utc)
        new_char = cls(name=name, description=description, max_version=1, last_save=current_time,
                       last_change=current_time, creator=creator)
        from .permission_models import UserPermissionsForChar
        with transaction.atomic():
            new_char.save()  # need to save at this point, because recomputing permissions may reload from db.
            # TODO: This causes last_save and last_change to be before creation time (by a tiny amount)
            UserPermissionsForChar.objects.create(char=new_char, user=creator)
        char_logger.info("User {creator} Created new char with name {name}".format(creator=creator, name=name))
        return new_char

    def create_root_char_version(self, *args, **kwargs) -> CharVersionModel:
        """
        Creates a new char version for this char (shortcut for a method of CharModel)
        Refer to CharVersionModel.create_root_char_version for details
        """
        if 'owner' in kwargs:
            raise ValueError("Use class method CharVersionModel.create_char_version to change owner")
        return CharVersionModel.create_root_char_version(*args, **kwargs, owner=self)

    def may_be_read_by(self, *, user: CGUser) -> bool:
        """
        shorthand to check read permissions.
        """
        from .permission_models import CharUsers
        return CharUsers.user_may_read(char=self, user=user)

    def may_be_written_by(self, *, user: CGUser) -> bool:
        """
        shorthand to check read/write permission.
        """
        from .permission_models import CharUsers
        return CharUsers.user_may_write(char=self, user=user)

    def validate_treeness(self) -> None:
        """
        Checks that the parent-relation gives a directed forest for the versions of a given char.
        Raises an exception if not.
        soft-O(n^2) algorithm for stupid reasons (next(filter...)), but too lazy to change.
        TODO: Currently unused and untested
        """
        cvs = list(CharVersionModel.objects.filter(owner=self))
        for cv in cvs:
            if (cv.parent is not None) and cv.parent not in cvs:
                raise IntegrityError("char version's parent's owner != owner")
        check_cvs: List[Optional[int]] = [None] * len(cvs)
        indices = range(len(cvs))
        for i in range(len(cvs)):
            if check_cvs[i] is not None:
                continue
            j = i
            while check_cvs[j] is None:
                check_cvs[j] = i
                target = cvs[j].parent
                if target is None:
                    break
                j = next(filter(lambda index: cvs[index] == target, indices))
            else:  # No break in while loop
                if check_cvs[j] == i:
                    raise IntegrityError("Char version's parent relation has a cycle")
        assert all(x is not None for x in check_cvs)


class CharVersionModel(models.Model):
    """
    Data stored in the database for a char version. Note that many CharVersionModels belong to a single CharModel

    Signals: pre-delete: TODO: Needs to be redone
    """

    class Meta(MyMeta):
        get_latest_by = 'creation_time'

    # Name of the char. This is included in CharVersionModel to allow renames.
    # If empty, we take the owning CharModel's name.
    version_name: str = models.CharField(max_length=CHAR_NAME_MAX_LENGTH, blank=True, default="")

    @property
    def name(self) -> str:
        """
        Given name of the character version. This is typically the name of the character.
        :return:
        """
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
    # TODO: We have on_delete = models.PROTECT now, pre_delete signal should fail.
    # NOTE: parent is mostly for informational purposes.
    # Actual semantic references are tracked by CVReferencesModel (with refers_to and referred_by reverses here)
    parent: Optional[CharVersionModel] = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True,
                                                           related_name='children', related_query_name='child')
    # Note that these should be thought of as a m2m model trough CVReferencesModel.
    # (We need multiple relations between the same pair to be possible, which ManyToMany models do not support)
    references_from: RELATED_MANAGER_TYPE[CharVersionModel]  # reverse to foreign key from CVReferencesModel
    references_to: RELATED_MANAGER_TYPE[CharVersionModel]  # reverse to foreign key from CVReferencesModel
    children: RELATED_MANAGER_TYPE[CharVersionModel]  # reverse to foreign key parent

    # JSON metadata to initialize the data sources
    json_config: str = models.TextField(blank=True)
    # Edit mode. This is actually determined by json_config. Access as edit_mode (which has the correct enumeration type)
    _edit_mode: int = models.IntegerField(default=EditModes.NORMAL.value, choices=EditModesChoices)
    # owning char
    owner: CharModel = models.ForeignKey(CharModel, on_delete=models.CASCADE, related_name='versions', related_query_name='char_version')

    objects: MANAGER_TYPE[CharVersionModel]

    @classmethod
    def make_dummy(cls, pk: int) -> CharVersionModel:
        """
        Creates a "dummy object with a given primary key". This key is not necessarily present in the db and at any rate
        should not be saved.

        While this is not a valid CharVersion object, it can be used in foreign-key queries.
        This is really only used as a workaround to limitations of Django.

        TODO: Untested? May need to set more values.
        """
        ret = cls(pk=pk)
        ret.is_dummy = True
        return ret

    @property
    def edit_mode(self)->EditModes:
        return EditModes(self._edit_mode)

    @property
    def can_create_overwriter(self) -> bool:
        """
        Can we create a char version for overwriting it?
        This is disallowed if other char versions refer to it.
        """
        return not self.references_to.exists()

    @edit_mode.setter
    def edit_mode(self, new_edit_mode: EditModes):
        self._edit_mode = new_edit_mode.value

    def __str__(self) -> str:
        if self.edit_mode:
            return self.name + " V" + str(self.char_version_number) + "+"
        else:
            return self.name + " V" + str(self.char_version_number)

    @classmethod
    def create_root_char_version(cls, *, version_name: str = "", description: str = "",
                                 json_config: str = None, python_config: PythonConfigRecipe = None, owner: CharModel,
                                 edit_mode: EditModes = None) -> CharVersionModel:
        """
        Creates a brand new (root) char version that does not have a parent.

        The new version's edit_mode is determined by json_config / python_config. The edit_mode parameter may only be
        used in conjunction with python_config and will override it.

        Note that create_root_char_version makes a (deep) copy of the received python_config.
        """

        #  To avoid surprises: CVConfig assumes sole ownership of passed python_config and we actaully modify python_config.
        #  Shallow copy should be OK in this particular case, as CVConfig.__init__ makes a deepcopy anyway.
        python_config = copy.copy(python_config)
        char_logger.info("Creating new root char version for CharModel {0!s} (pk {1}).".format(owner, owner.pk))
        if (json_config is None) == (python_config is None):
            raise ValueError("Exactly one of json_config or python_config must be provided")
        if edit_mode is not None:
            if python_config is None:
                raise ValueError("explicitly setting edit_mode only available with python_config")
            python_config.edit_mode = edit_mode

        # This just serves for the json<->python conversion, really. We can avoid doing that during a transaction.
        new_config: CVConfig = CVConfig(from_json=json_config, from_python=python_config, validate_syntax=True, setup_managers=False)
        json_config = new_config.json_recipe

        with transaction.atomic():

            owner.refresh_from_db()
            # We create a new version now in oder to get a primary key in the database:
            try:
                new_char_version: CharVersionModel = CharVersionModel(version_name=version_name,
                                                                      json_config=json_config,
                                                                      char_version_number=owner.max_version,
                                                                      last_changed=datetime.now(timezone.utc),
                                                                      description=description,
                                                                      edit_counter=1,
                                                                      parent=None,
                                                                      _edit_mode=new_config.edit_mode.as_int(),
                                                                      owner=owner)
                new_char_version.save()
                char_logger.info("New CharVersionModel {0!s} created with pk {1}".format(new_char_version, new_char_version.pk))
                # Re-create the config with the associated primary key and tell CVConfig that it is a new version.
                # (This may trigger hooks in the associated managers)

                new_config = CVConfig.create_char_version_config(from_python=new_config.python_recipe, db_char_version=new_char_version, setup_managers=True, db_write_back=False)
                # CVConfig.create_char_version_config might change the config:
                # TODO: allow db_write_back=True above instead.
                if json_config != new_config.json_recipe:
                    new_char_version.json_config = new_config.json_recipe
                    new_char_version.save()
                owner.max_version += 1
                owner.save()
                CVReferencesModel.check_reference_validity_for_char_version(new_char_version)
            except Exception:
                char_logger.exception("Failed to create char version")
                raise
        return new_char_version

    @classmethod
    def derive_char_version(cls, *, parent: CharVersionModel, owner: CharModel = None, edit_mode: EditModes = None) -> CharVersionModel:
        """
        Makes a new char version based on a previous one.
        Both owner and parent are assumed to be saved in the db.
        parent.owner may be unequal to owner: In this case, we create a a copy of parent as
        a new root char version for owner.

        Note that this function may change owner / parent.owner to set metadata such as last_changed.
        TODO: Consider allowing to override python/json-config
        """

        char_logger.info("Deriving new char version from CharVersion {0!s}".format(parent))

        transplant: bool = bool(owner and owner!=parent.owner)
        with transaction.atomic():
            parent.refresh_from_db()
            if owner is not None:
                owner.refresh_from_db()
            else:
                owner = parent.owner
            # Note: Avoid assumptions on the meaning of bool(edit_mode)
            new_edit_mode: EditModes = edit_mode if (edit_mode is not None) else parent.edit_mode
            overwrite = new_edit_mode.is_overwriter()
            new_version: CharVersionModel = cls.objects.get(pk=parent.pk)
            new_version.pk = None
            if transplant:
                # This should raise some error later anyway...
                if overwrite:
                    raise ValueError("Cannot set char for overwrite in transplant mode")
                new_version.parent = None
                new_version.owner = owner
            else:
                new_version.parent = parent  # keep owner
            if not overwrite:  # In overwrite mode, we keep the old char_version_number.
                new_version.char_version_number = owner.max_version
                owner.max_version += 1
                owner.save()
            # save with empty (and invalid!) json_config to create a db entry
            new_version.json_config = ""
            new_version.save()
            if overwrite:
                if not parent.can_create_overwriter:
                    raise ValueError("Cannot edit char for overwriting: Other versions of this char refer to it.")
                CVReferencesModel.objects.create(source=new_version, target=parent, reason_str="Overwrite target",
                                                 ref_type=CVReferencesModel.ReferenceType.OVERWRITE.value)
            parent_config = CVConfig(from_json=parent.json_config, validate_syntax=True, setup_managers=True, validate_setup=True, db_char_version=parent)
            new_config = parent_config.copy_config(target_db=new_version, new_edit_mode=edit_mode, transplant=transplant, db_write_back=False)
            new_version.json_config = new_config.json_recipe
            new_version.edit_mode = new_config.edit_mode
            new_version.edit_counter += 1
            new_version.save()
            new_version.check_reference_validity()
        return new_version

    def may_be_read_by(self, *, user: CGUser) -> bool:
        from .permission_models import CharUsers
        return CharUsers.user_may_read(char=self, user=user)

    def may_be_written_by(self, *, user: CGUser) -> bool:
        from .permission_models import CharUsers
        return CharUsers.user_may_write(char=self, user=user)

    def check_reference_validity(self):
        CVReferencesModel.check_reference_validity_for_char_version(char_version=self)


class CVReferencesModel(models.Model):
    """
    Intermediate class for CharVersion -> CharVersion semantic references.
    We have an entry here whenever a CharVersion refers to another CharVersion
    (and effectively locks the target!)

    Constraints:
    source != target (restriction may be removed, but we check it for now)
    source.owner == target.owner
    target.edit_mode in ALLOWED_REFERENCE_TARGETS (list defined in EditModes.py)

    Furthermore, CVReference has some "owner" that is responsible for creating/deleting it, depending on ref_type.
    For ref_type OVERWRITE, this is the source itself, which must have edit_mode.is_overwriter() == True.
    We would like to enforce these checks at the DB level, but cannot do so with Django.
    """
    class Meta(MyMeta):
        pass

    class ReferenceType(models.IntegerChoices):
        OVERWRITE = 1

    source: CharVersionModel = models.ForeignKey(CharVersionModel, on_delete=models.CASCADE, related_name='references_from')
    target: CharVersionModel = models.ForeignKey(CharVersionModel, on_delete=models.PROTECT, related_name='references_to')
    reason_str: str = models.CharField(max_length=200, blank=False, null=False)
    ref_type: int = models.IntegerField(choices=ReferenceType.choices, default=ReferenceType.OVERWRITE.value)
    objects: MANAGER_TYPE[CVReferencesModel]

    def check_validity(self) -> None:
        """
        Checks validity constraints for this CVReference (assumed to be in sync with DB).
        We cannot include these constraints at the DB level with django because it involves joins.
        Indicates failure by raising an IntegrityError.
        """
        if self.source == self.target:
            # Self-references would be doable, but they would require special handling and it's not worth the pain.
            raise IntegrityError("CharVersion reference to itself")
        if self.source.owner != self.target.owner:
            raise IntegrityError("CharVersion references only allowed with the same Char model")
        if self.target.edit_mode not in ALLOWED_REFERENCE_TARGETS:
            raise IntegrityError("CharVersion reference to target that does not allow being references")
        if self.ref_type == self.ReferenceType.OVERWRITE.value:
            if self.source.edit_mode.is_overwriter() is False:
                raise IntegrityError("CharVersion references overwrite target, but but source has wrong type")
            if type(self).objects.filter(target=self.target).count() != 1:
                raise IntegrityError("CharVersion references overwrite target, but target has other references to it.")

    @classmethod
    def check_reference_validity_for_char_version(cls, /, char_version: CharVersionModel) -> None:
        """
        Checks validity constraints for all References involving char_version (assumed to be in sync with DB)
        """
        for source_references in cls.objects.filter(source=char_version):
            source_references.check_validity()
        for target_references in cls.objects.filter(target=char_version):
            target_references.check_validity()
        if char_version.edit_mode.is_overwriter() and \
                cls.objects.filter(source=char_version, ref_type=cls.ReferenceType.OVERWRITE.value).count() != 1:
            raise IntegrityError("Invalid number of overwrite targets")
        # TODO: Check managed
