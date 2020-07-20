"""
This file defines DBCharVersion, a class derived from BaseCharVersion. It provides an interface for manipulating
and retrieving data from char versions that were already saved in the DB.

This is the interface all queries that affect existing DB entries should go through.
"""
from __future__ import annotations
import contextlib
import logging
from typing import TYPE_CHECKING, Optional

from CharData import BaseCharVersion, NoReadPermissionError
from DBInterface.models import CharVersionModel, CGUser
from BackendInterface.TransactionClassWrapper import TransactionContextManagerWrapper

if TYPE_CHECKING:
    from CharVersionConfig import EditModes, CVConfig

logger = logging.getLogger("chargen.db_char_version")


class DBCharVersion(BaseCharVersion):
    """
    A DBCharVersion is an (or THE) interface for querying and manipulating char versions that already exist in the
    database. The intented usage is
    with DBCharVersion.start_transaction(pk = primary_database_key, ...) as char_version:
       do stuff with char_version

    Alternatively, use char_version = DBCharVersion(pk = primary_database_key, ...) if already in a transaction.
    Note: Creating the DBCharVersion object and all operations on it need to be contained in a single DB transaction.
          This is due to data races with permissions checking.
    """

    _db_instance: CharVersionModel

    # When delay_saving is set to True, saving of metadata to db is delayed until delay_saving is reset to False.
    # Intended usage is "with self.delayed_metadata_saving(): ..."
    # This is used internally to avoid costly updates to last_changed after every sub(!)-request.
    _delay_saving: bool
    _needs_saving: bool  # Records whether we need to save metadata back to db upon clearing delay_saving

    # Controls whether updates to the configuration should automatically be saved back to DB.
    # (Changes behaviour of super().methods)
    db_write_back = True

    # set on an instance-by-instance basis. This is just a more conservative default to guard against bugs.
    data_write_permission = False
    config_write_permission = False
    # TODO: Setting those during __init__ requires some DB hits.
    #       Consider turning into properties and delay hitting DB until request.

    def __init__(self, *, pk=None, db_instance: CharVersionModel = None,
                 data_write_permission: bool = None, config_write_permission: bool = None, for_user: CGUser = None,
                 _delay_save_until_transaction: bool = False,
                 version_name: str = None, description: str = None):
        """
        Initializes a DBCharVersion object that is associated with a given CharVersionModel database instance.
        Note that the instance needs to already exist in the database and is expected to be fresh.

        Either pk or db_instance must be given to specify the CharVersionModel instance either by a primary key in
        the database or the model instance itself.
        Invalid pk's will raise CharVersionModel.DoesNotExist (subclass of Exception)
        TODO: Log and reraise as 404 or ValueError?

        Either both data_write_permissions and config_write_permissions or for_user needs to be given.
        This sets the permissions for accesses through this DBCharVersion, taking restrictions from edit_mode into
        account.

        version_name and description are passed to super().__init__. This can be used to
        cause metadata to be written to, which triggers saving in the db via the overridden properties.

        _delay_save_until_transaction must only be set if created from DBCharVersion.start_transaction with
        appropriate parameters.
        """

        if (pk is None) == (db_instance is None):
            raise ValueError("Need to give either pk or db_instance")
        if (data_write_permission is None) == (for_user is None):
            raise ValueError("Need to give either data_write_permission or for_user")
        if (config_write_permission is None) == (for_user is None):
            raise ValueError("Need to give either config_write_permission or for_user")
        if db_instance:
            if db_instance.pk is None:
                raise RuntimeWarning("associated db_instance is not in database")
            # Must not give fake db_instances that only have pk, since we save() it
            # Use the pk= interface if you only have a pk.
            assert not getattr(db_instance, 'is_dummy', False)
            self._db_instance = db_instance
        else:
            self._db_instance = CharVersionModel.objects.get(pk=pk)  # Will raise exception if pk is not in db.

        # Note: edit mode is stored both in the config (which is set up in super() below) and in the model.
        edit_mode = self._db_instance.edit_mode  # Needed to set up permissions.

        assert (data_write_permission is None) == (config_write_permission is None)
        if data_write_permission is None:  # and also config_write_permission
            # TODO: DB interface that gets both read and write permissions simultaneously.
            if for_user.may_write_char(char=self._db_instance):
                self.data_write_permission = edit_mode.may_edit_data()
                self.config_write_permission = edit_mode.may_edit_config()
            else:
                if not for_user.may_read_char(char=self._db_instance):
                    raise NoReadPermissionError
                self.data_write_permission = False
                self.config_write_permission = False
        else:
            if data_write_permission and not edit_mode.may_edit_data():
                raise ValueError("passed value of data_write_permission conflicts with edit_mode")
            self.data_write_permission = data_write_permission
            if config_write_permission and not edit_mode.may_edit_config():
                raise ValueError("passed value of config_write_permission conflicts with edit_mode")
            self.config_write_permission = config_write_permission

        self._delay_saving = _delay_save_until_transaction
        self._needs_saving = False

        with self.delayed_metadata_saving():
            super().__init__(json_config=self._db_instance.json_config, version_name=version_name, description=description)

    @classmethod
    def start_transaction(cls, /, delayed_metadata_saving: bool = False, *args, **kwargs):
        """
        Return a Context Manager whose __enter__ method starts a transaction and returns cls(*args, **kwargs)
        Setting delayed_metadata_saving causes most metadata db writes to be delayed until the context manager block
        exits without an exception.

        Intended usage is
        with DBCharVersion.atomic(pk = ...) as db_char_version:  # Arguments are as in DBCharVersion(pk = ...)
           ...

        This is mostly equivalent to
        with transaction.atomic():
           db_char_version = DBCharVersion(pk = ...)
           ....
        """
        if delayed_metadata_saving:
            def _at_exit(db_char_version: BaseCharVersion) -> None:
                db_char_version._delay_saving = False
            return TransactionContextManagerWrapper(*args, _cls=cls, _at_exit=_at_exit, _delay_save_until_transaction=True, **kwargs)
        else:
            return TransactionContextManagerWrapper(*args, _cls=cls, **kwargs)

    @property
    def config(self) -> Optional[CVConfig]:
        """
        self._config contains self._db_instance and assumes this to be in sync with the DB.
        """
        if self._needs_saving:
            self._save(force=True)
        return self._config

    @property
    def edit_mode(self, /) -> EditModes:
        return self._db_instance.edit_mode

    @property
    def db_instance(self, /) -> CharVersionModel:
        if self._needs_saving:
            self._save(force=True)
        return self._db_instance

    def _save(self, /, force: bool = False) -> None:
        """
        Saves local changes to _db_instance back to db.

        Note: We assume that all db changes through a given DBCharVersion instances are contained in a single transaction.
        If _delay_saving is set, we delay the DB write-back unless force is set.
        """
        if force or not self._delay_saving:
            if self._db_instance.edit_mode != self.config.edit_mode:
                self._db_instance.edit_mode = self.config.edit_mode
                logger.critical("DBCharVersion: edit modes in config and db were out of sync")
            self._db_instance.save()
            self._needs_saving = False
        else:
            self._needs_saving = True  # Causes _save to be called again as soon as delay_saving is set to False.

    @property
    def delay_saving(self, /) -> bool:
        return self._delay_saving

    @delay_saving.setter
    def delay_saving(self, value: bool, /) -> None:
        self._delay_saving = value
        if (not value) and self._needs_saving:
            self._save()

    @contextlib.contextmanager
    def delayed_metadata_saving(self, /):
        """
        Returns a context manager that delays saving back metadata to db during its scope.
        """
        old = self.delay_saving  # In case of nested with ... finally ...  blocks.
        self.delay_saving = True
        try:
            yield
        finally:
            self.delay_saving = old

    class _Meta:
        @staticmethod
        def bind_to_db(name: str, /, create_setter: bool = True) -> property:
            """
            Creates a property object to bind attribute names of DBCharVersion to attributes of models.CharVersionModel
            via DBCharVersion._db_instance.
            """
            assert hasattr(CharVersionModel, name)

            def getter(s: DBCharVersion, /):
                return getattr(s._db_instance, name)
            doc = "attribute %s of DBCharVersion, bound to db" % name

            def deleter(s: DBCharVersion, /):
                raise ValueError("Cannot delete attribute bound to db")

            if create_setter:
                @BaseCharVersion._Decorators.requires_write_permission
                def setter(s: DBCharVersion, value, /):
                    setattr(s._db_instance, name, value)
                    s._save()
            else:
                setter = None
            return property(getter, setter, deleter, doc)

    # This makes e.g. self.creation_time equivalent to self._db_instance.creation_time
    # with a possibly delayed setter that saves to the DB.
    creation_time = _Meta.bind_to_db('creation_time', create_setter=False)
    description = _Meta.bind_to_db('description')
    name = _Meta.bind_to_db('name', create_setter=False)
    version_name = _Meta.bind_to_db('version_name')

    # Special case: The value of last_changed in the DB is set automatically whenever we call CharVersionModel.save().
    # This also syncs the DB with _db_instance.
    # As a consequence, _db_instance.last_changed is out of sync with db if we delay any saving.
    @property
    def last_change(self, /):
        if self._needs_saving:
            self._save(force=True)
        return self._db_instance.last_changed

    @last_change.setter
    def last_change(self, value, /):
        self._save()

    def _update_last_changed(self) -> None:
        self._save()

