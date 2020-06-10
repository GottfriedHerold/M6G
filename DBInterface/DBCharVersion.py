from CharData.BaseCharVersion import BaseCharVersion
from CharData.DataSources import CharDataSource
from .models import DictEntry, MANAGER_TYPE
from collections import abc

# class GenericDBDataSource(CharDataSource):
#    dict_manager: MANAGER_TYPE[DictEntry]  # to be set to the appropriate models.objects Manager

class NaiveDBAsDict(abc.MutableMapping):
    pass