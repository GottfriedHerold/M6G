"""
Defines data source classes that relate to the database.
"""
from CharData.CharVersionConfig import CVConfig, BaseCVManager
from .models import MANAGER_TYPE, ShortDictEntry, LongDictEntry, DictEntry, SimpleDBToDict, CharVersionModel
from CharData import DataSourceBase
import logging
from typing import TYPE_CHECKING, List, ClassVar


logger = logging.getLogger('chargen.dbdatasources')

class NaiveDBDataSource(DataSourceBase.CharDataSourceBase):
    dict_type = "ShortDB"
    stores_input_data = True
    stores_parsed_data = False
    contains_restricted = False
    contains_unrestricted = True
    description = "DB-backed data source"
    type_unique = True
    default_write = True
    read_only = False

    _default_manager: ClassVar = ShortDictEntry.objects

    def __init__(self, *, manager: MANAGER_TYPE[DictEntry] = None, char_version_model: CharVersionModel,
                 dict_type: str = None, description: str = None, default_write: bool = None, type_unique: bool = None):
        if dict_type:
            self.dict_type = dict_type
            if (default_write is None) or (type_unique is None) or (manager is None):
                raise ValueError("Need to specify default_write, type_unique and manager for custom dict_type")
        if description:
            self.description = description
        if manager is None:
            manager = type(self)._default_manager
        if type_unique is not None:
            self.type_unique = type_unique
        if default_write is not None:
            self.default_write = default_write
        self.input_data = SimpleDBToDict(manager=manager, char_version_model=char_version_model)

class LongEntryNaiveDBDataSource(NaiveDBDataSource):
    _default_manager = LongDictEntry.objects
    default_write = False
    dict_type = "LongDB"

# class NaiveDBDataSourceManager(BaseCVManager):
#     def make_data_source(self, *, target: List['DataSourceBase.CharDataSourceBase']):
#         db_cv_pk = self.cv_config.db_char_version.pk  # Note that .db_char_version raises an error if misused.
#
#         def prepend_db_data_sources(data_sources):
#             return [NaiveDBDataSource(char_version_model_pk=db_cv_pk), LongEntryNaiveDBDataSource(char_version_model_pk=db_cv_pk)] + data_sources
#
#         self.cv_config.add_to_end_of_post_process_queue(prepend_db_data_sources)
#         return target
#
#     def copy_config(self, target_recipe: dict, /, *, new_edit_mode: bool, transplant: bool, target_db) -> None:
#         super().copy_config(target_recipe, new_edit_mode=new_edit_mode, transplant=transplant, target_db=target_db)
#         ShortDictEntry.copy_between_charversions(source=self.cv_config.db_char_version, target=target_db)
#         LongDictEntry.copy_between_charversions(source=self.cv_config.db_char_version, target=target_db)
