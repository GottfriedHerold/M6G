"""
This file implements the CharDataSourceBase class, which is the class all other DataSources are derived from.
It implements the common interface and some sensible defaults that simplify deriving from it.
"""

from typing import Union, Mapping, MutableMapping, Any, Iterable, Dict, Optional, ClassVar

from CharData import Parser, Regexps
import logging
logger = logging.getLogger("chargen.data_sources")

class CharDataSourceBase:
    """
    Abstract Base class for Char Data sources.

    A Char Data source is where CharVersions get their data from. In essence, it is a key-value store that provides
    (up to) two interfaces: One interface for storing / retrieving user input strings that adhere to the
    Chargen Expression language, and another interface for storing / retrieving parsed results.
    """

    # These two are not necessarily enforced by the setters or the underlying container(s); violating the restrictions
    # this will make lookup fail to find things in unspecified ways.
    contains_restricted: bool = True  # Data source may contain restricted keys.
    contains_unrestricted: bool = True  # Data source may contain unrestricted keys.
    # description and dict_type are string that describe the data source.
    # If appropriately unique, BaseCharVersion can look up the data source by either description/dict_type or their combination.
    description: str = "nondescript"
    dict_type: str = "user defined"  # This may be overridden at the class or instance level.
    type_unique: bool = False  # At most one data source with the given dict_type must be present in a BaseCharVersion.
    # Note that defining multiple DataSource classes with the same dict_type, but only some setting type_unique may
    # or may not work as intended (as in: may not detect errors)

    default_write: bool = False  # Writes go into this data source by default. At most one data source per BaseCharVersion.
    read_only: bool = False  # Cannot write / delete if this is set.
    # At least one of these two must be set by derived class. We do not allow setting this on the instance level.
    stores_input_data: ClassVar[bool]  # stores input data. Set by __init_subclass__ to False if unset.
    stores_parsed_data: ClassVar[bool]  # stores parsed data. Set by __init_subclass__ to False if unset.

    # The following class/object attributes are not part of the interface, but employed by the default implementation.

    # One or both of these two need to be set by a derived class to make CharDataSourceBase's default methods work:
    # (alternatively, override all methods that use input_data/parsed_data)
    input_data: Union[Mapping, MutableMapping]  # self.input_data is where input data is stored if stored_input_data is set
    parsed_data: Union[Mapping, MutableMapping]  # self.parsed_data is where parsed data is stored if stores_parsed_data is set

    input_parser = staticmethod(Parser.input_string_to_value)  # parser to transform input values to parsed_data.

    # TODO: dir - like functions that return all keys (possibly filtered by prefix, possibly only return prefixes etc.)
    # Note that the Chargen Expression Language should expose these by a special key (in order to facilitate dependency tracking for caching)
    # TODO: (prefix?) restriction

    # TODO: We may remove this in favor of query-level prefix restrictions.
    def _check_key(self, key: str) -> bool:
        """
        The default implementation runs this on keys before some operations to check whether the key may even be
        in input_data resp. parsed_data. This is purely an optimization for the case where
        lookups in stores_input_data or stores_parsed_data are expensive (i.e. database access)
        Always returning true is perfectly fine. It is up to the concrete class to ensure this optimization works.
        Do not rely on the setters checking this.
        :param key: key to look up
        :return: False if we can somehow guarantee that this key does not belong into this data source.
        """
        if not Regexps.re_key_any.fullmatch(key):
            return False
        if not self.contains_restricted and Regexps.re_key_restrict.fullmatch(key):
            return False
        if not self.contains_unrestricted and not Regexps.re_key_restrict.fullmatch(key):
            return False
        return True

    def __init_subclass__(cls, abstract: bool = False, **kwargs):
        super().__init_subclass__(**kwargs)
        if not (abstract or cls.stores_input_data or cls.stores_parsed_data):
            raise AssertionError("Data source class must set at least one of stores_input_data or stores_parsed_data to True")

    def __contains__(self, key: str) -> bool:
        """
        Checks if key is contained in the data source
        """
        if not self._check_key(key):
            return False
        if self.stores_input_data:
            return key in self.input_data
        else:
            return key in self.parsed_data

    def __getitem__(self, key: str) -> Any:
        """
        Gets the parsed item stored under this key.
        TODO: Is raising KeyError on non-existent keys a requirement? Alternative is doing arbitrary DataSource-dependent other things like raising a different exception.
        """
        if self.stores_parsed_data:
            return self.parsed_data[key]
        else:
            return self.input_parser(self.input_data[key])

    def bulk_get_items(self, keys: Iterable[str]) -> Dict[str, Any]:
        """
        Get multiple data. Returns a dict. The default delegates to __getitem__, but may be overridden for efficiency.
        TODO: Prescribe behaviour on non-existent keys? Default?
        """
        return {key: self[key] for key in keys}

    def __setitem__(self, key: str, value: object) -> None:
        """
        Sets the ("parsed", i.e. raw python) value stored under key.
        Note that if the data source stores input data, this function makes no sense and we raise an Error.
        (This would make parsed and input data inconsistent)
        """
        if not self._check_key(key):
            raise KeyError("Data source does not support storing this key")
        if self.stores_input_data or self.read_only:
            raise TypeError("Data source does not support storing parsed data")
        assert self.stores_parsed_data
        self.parsed_data[key] = value

    def bulk_set_items(self, key_vals: Dict[str, object]) -> None:
        """
        sets several parsed data at once. May be overridden for efficiency
        """
        for key, val in key_vals.items():
            self[key] = val

    def __delitem__(self, key: str) -> None:
        """
        Deletes the key from the data source. This assumes that the key was present beforehand.
        TODO: Prescribe behaviour if key not present?
        """
        if not self._check_key(key):
            raise KeyError("Data source does not support deleting this key")
        if self.stores_parsed_data:
            del self.parsed_data[key]
        if self.stores_input_data:
            del self.input_data[key]

    def bulk_del_items(self, keys: Iterable[str]) -> None:
        """
        Deletes the keys from the data source. Works like __delitem__. May be overridden for efficiency.
        """
        for key in keys:
            del self[key]

    def get_input(self, key: str, default="") -> Optional[str]:
        """
        Gets the input data associated to the key, or default = "" if not found.

        Note: If we do not store input data, returns None. This may be overwritten by a derived class to return
        an error message string. It must *not* throw an exception in that case.
        The default = "" behaviour (which is relevant iff the data source stores actual input data) must NOT be overwritten.
        """
        if not self.stores_input_data:
            return None
        else:
            try:
                return self.input_data[key]
            except KeyError:
                return default

    def bulk_get_inputs(self, keys: Iterable[str], default="") -> Dict[str, str]:
        """
        Gets several input data at once. May be overwritten for more efficiency.
        Returns a dict key:value with value as in get_input
        """
        return {key: self.get_input(key, default=default) for key in keys}

    def set_input(self, key: str, value: str) -> None:
        """
        Stores value (as an input string, to be parsed with input_parser) under key.
        Storing an empty value will delete the key, if it was present before.
        """
        if self.read_only:
            raise TypeError("Data source is read-only")
        if not self._check_key(key):
            raise KeyError("Data source does not support storing this key")
        if not value:
            try:
                del self[key]
            except KeyError:
                pass
        else:
            if self.stores_input_data:
                self.input_data[key] = value
            if self.stores_parsed_data:
                self.parsed_data[key] = self.input_parser(value)

    def bulk_set_inputs(self, key_vals: Dict[str, str]) -> None:
        """
        Sets several inputs at once. input is a dict {key: values}.
        The default delegates to set_input, but it may be overridden for efficiency.
        """
        for key, val in key_vals.items():
            self.set_input(key, val)

    def __str__(self, /) -> str:
        return "Data source of type " + self.dict_type + ": " + self.description


