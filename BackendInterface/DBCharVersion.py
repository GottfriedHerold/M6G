from __future__ import annotations
import contextlib
import logging


from CharData import BaseCharVersion, NoReadPermissionError
from DBInterface.models import CharVersionModel, CGUser
from DBInterface.TransactionClassWrapper import TransactionContextManagerWrapper

logger = logging.getLogger("chargen.db_char_version")

# class GenericDBDataSource(CharDataSourceBase):
#    dict_manager: MANAGER_TYPE[DictEntry]  # to be set to the appropriate models.objects Manager

class DBCharVersion(BaseCharVersion):
    _db_instance: CharVersionModel

    _delay_saving: bool  # When delay_saving is set to True, saving of metadata to db is delayed until delay_saving is reset to False.
    # Intended usage is "with self.delayed_metadata_saving(): ..."
    # This is used internally to avoid costly updates to last_changed after every sub-request.

    _needs_saving: bool  # Records whether we need to save metadata back to db upon clearing delay_saving

    def __init__(self, *, pk=None, db_instance: CharVersionModel = None,
                 write_permission: bool = None, for_user: CGUser = None,
                 _delay_save_until_transaction: bool = False,
                 **kwargs):
        """
        Initializes a DBCharVersion object that is associated with a given CharVersionModel database instance.
        Note that the instance needs to already exist in the database and is expected to be fresh.

        Either pk or db_instance must be given to specify the CharVersionModel instance either by a primary key in
        the database or the model instance itself. Invalid pk's will raise CharVersionModel.DoesNotExist (subclass of Exception)
        TODO: Log and reraise as 404 or ValueError?
        Other parameters are passed to super().__init__. This can be used to
        cause metadata to be written to, which triggers saving in the db via the overridden properties.
        TODO: Specify allowed **kwargs
        """

        if (pk is None) == (db_instance is None):
            raise ValueError("Need to give either pk or db_instance")
        if (write_permission is None) == (for_user is None):
            raise ValueError("Need to give either write_permission or for_user")
        if db_instance:
            if db_instance.pk is None:
                raise RuntimeWarning("associated db_instance is not in database")
            self._db_instance = db_instance
        else:
            self._db_instance = CharVersionModel.objects.get(pk=pk)  # Will raise exception if pk is not in db.
        if write_permission is None:
            if for_user.may_write_char(char=self._db_instance):
                self.write_permission = True
            else:
                if not for_user.may_read_char(char=self._db_instance):
                    raise NoReadPermissionError
                self.write_permission = False
        else:
            self.write_permission = write_permission
        self._delay_saving = _delay_save_until_transaction
        self._needs_saving = False

        with self.delayed_metadata_saving():
            super().__init__(json_config=self._db_instance.json_config, **kwargs)

    @classmethod
    def atomic(cls, /, delayed_metadata_saving: bool = False, *args, **kwargs):
        """
        Return a Context Manager whose __enter__ method starts a transaction and returns cls(*args, **kwargs)
        delayed_metadata_saving causes most metadata db writes to be delayed until the context manager block
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
            return TransactionContextManagerWrapper(*args, _cls=cls, _at_exit=_at_exit, **kwargs)
        else:
            return TransactionContextManagerWrapper(*args, _cls=cls, **kwargs)

    @property
    def db_instance(self, /) -> CharVersionModel:
        return self._db_instance

    def _save(self, /, force: bool = False) -> None:
        """
        Saves local changes to _db_instance back to db.

        Note: We assume that all db changes through a given DBCharVersion instances are contained in a single transaction.
        If _delay_saving is set, we delay the DB write-back unless force is set.
        """
        if force or not self._delay_saving:
            self._db_instance.edit_mode = self.config.edit_mode  # TODO
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
        old = self.delay_saving  # In case of nested with ... finally ...  blocks.
        self.delay_saving = True
        try:
            yield
        finally:
            self.delay_saving = old

    class _Meta:
        @staticmethod
        def bind_to_db(name: str, create_setter: bool = True) -> property:  # Used to bind attribute names of DBCharVersion to attributes of models.CharVersionModel via DBCharVersion._db_instance
            assert hasattr(CharVersionModel, name)

            def getter(s: DBCharVersion, /):
                return getattr(s._db_instance, name)
            doc = "attribute %s of DBCharVersion, bound to db" % name

            def deleter(s: DBCharVersion, /):
                raise ValueError("Cannot delete attribute bound to db")

            if create_setter:
                def setter(s: DBCharVersion, value, /):
                    setattr(s._db_instance, name, value)
                    s._save()
            else:
                setter = None
            return property(getter, setter, deleter, doc)

    # This makes e.g. self.creation_time equivalent to self._db_instance.creation_time with a possibly delayed setter.
    creation_time = _Meta.bind_to_db('creation_time')
    last_change = _Meta.bind_to_db('last_changed')
    description = _Meta.bind_to_db('description')
    name = _Meta.bind_to_db('name', create_setter=False)
    version_name = _Meta.bind_to_db('version_name')
