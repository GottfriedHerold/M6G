from CharData.BaseCharVersion import BaseCharVersion
from CharData.DataSources import CharDataSource
from CharData.CharVersionConfig import CVConfig
from collections import abc
from . import models
import contextlib
from typing import Union

# class GenericDBDataSource(CharDataSource):
#    dict_manager: MANAGER_TYPE[DictEntry]  # to be set to the appropriate models.objects Manager

class DBCharVersion(BaseCharVersion):
    _db_instance: models.CharVersionModel
    _delay_saving: bool  # When delay_saving is set to True, saving of metadata to db is delayed until delay_saving is reset to False.
        # Intended usage is "with self.delayed_metadata_saving(): ..."
    _needs_saving: bool  # Records whether we need to save metadata back to db upon clearing delay_saving

    def __init__(self, *, pk=None, db_instance: models.CharVersionModel = None, **kwargs):
        """
        Initializes a DBCharversion object that is associated with a given CharVersionModel instance.
        Note that the instance typically already exist in the database.
        TODO: Do we need / allow db_instance.pk == None, so saving it will assign a pk?
        Either pk or db_instance must be given to specify the CharVersionModel instance either by a primary key in
        the database or the model instance itself. Invalid pk's will raise CharVersionModel.DoesNotExist (subclass of Exception)
        TODO: Log and reraise as 404 or ValueError?
        Other parameters are passed to super().__init__. This can be used to
        cause metadata to be written to, which triggers saving in the db via the overridden properties.
        TODO: Specify allowed **kwargs
        """

        if (pk is None) == (db_instance is None):
            raise ValueError("Need to give either pk or db_instance")
        if db_instance:
            self._db_instance = db_instance
        else:
            self._db_instance = models.CharVersionModel.objects.get(pk=pk)  # May raise exception
        self._delay_saving = False
        self._needs_saving = False
        with self.delayed_metadata_saving():
            super().__init__(json_config=self._db_instance.json_config, **kwargs)

    @property
    def db_instance(self) -> models.CharVersionModel:
        return self._db_instance

    def save(self) -> None:
        if not self._delay_saving:
            self._db_instance.edit_mode = self.config.edit_mode
            self._db_instance.save()

    @property
    def delay_saving(self) -> bool:
        return self._delay_saving

    @delay_saving.setter
    def delay_saving(self, /, value: bool):
        self._delay_saving = value
        if (not value) and self._needs_saving:
            self.save()
            self._needs_saving = False

    @contextlib.contextmanager
    def delayed_metadata_saving(self):
        old = self.delay_saving  # In case of nested with ... finally ...  blocks.
        self.delay_saving = True
        try:
            yield
        finally:
            self.delay_saving = old

    class _Meta:
        @staticmethod
        def bind_to_db(name: str, create_setter: bool = True) -> property:  # Used to bind attribute names of DBCharVersion to attributes of models.CharVersionModel via DBCharVersion._db_instance
            assert hasattr(models.CharVersionModel, name)

            def getter(s: 'DBCharVersion'):
                return getattr(s._db_instance, name)
            doc = "attribute %s of DBCharVersion, bound to db" % name

            def deleter(s: 'DBCharVersion'):
                raise ValueError("Cannot delete attribute bound to db")

            if create_setter:
                def setter(s: 'DBCharVersion', /, value):
                    setattr(s._db_instance, name, value)
                    if s.delay_saving:
                        s._needs_saving = True
                    else:
                        s.save()
            else:
                setter = None
            return property(getter, setter, deleter, doc)

    # This makes e.g. self.creation_time equivalent to self._db_instance.creation_time with a possibly delayed setter.
    creation_time = _Meta.bind_to_db('creation_time')
    last_change = _Meta.bind_to_db('last_changed')
    description = _Meta.bind_to_db('description')
    name = _Meta.bind_to_db('name', False)
    version_name = _Meta.bind_to_db('version_name')



class NaiveDBAsDict(abc.MutableMapping):
    pass