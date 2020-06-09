from CharData.BaseCharVersion import BaseCharVersion, CharDataSource
from .models import DictEntry, MANAGER_TYPE
from collections import abc

# class GenericDBDataSource(CharDataSource):
#    dict_manager: MANAGER_TYPE[DictEntry]  # to be set to the appropriate models.objects Manager

class NaiveDBAsDict(abc.MutableMapping):
    pass