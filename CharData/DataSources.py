from typing import Union, Mapping, MutableMapping, Any, Iterable, Dict, Optional

from CharData import Parser, Regexps


class CharDataSource:
    """
    Abstract Base class for Char Data sources.
    This implements some common behaviour and is supposed to be overridden.
    """
    contains_restricted: bool = True  # Data source may contain restricted keys. Not necessarily enforced.
    contains_unrestricted: bool = True  # Data source may contain unrestricted keys.
    # description and dict_type are string that describe the data source.
    # If unique, BaseCharVersion can look up the data source by this.
    description: str = "nondescript"
    dict_type: str = "user defined"
    default_write: bool = False  # Writes go into this data source by default. At most one data source per BaseCharVersion.
    read_only: bool = False  # Cannot write / delete if this is set.
    stores_input_data: bool  # stores input data.
    stores_parsed_data: bool  # stores parsed data.
    type_unique: bool = False  # Only one data source with the given dict_type must be present in a BaseCharVersion.

    # One or both of these two need to be set by a derived class to make CharDataSource's default methods work:
    input_data: Union[Mapping, MutableMapping]  # self.storage is where input data is stored if stored_input_data is set
    parsed_data: Union[Mapping, MutableMapping]  # self.parsed_data is where parsed data is stored if stores_parsed_data is set

    input_parser = staticmethod(Parser.input_string_to_value)  # parser to transform input values to parsed_data.

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
        """
        if self.stores_parsed_data:
            return self.parsed_data[key]
        else:
            return self.input_parser(self.input_data[key])

    def bulk_get_items(self, keys: Iterable[str]) -> Dict[str, Any]:
        """
        Get multiple data. Returns a dict. May be overridden for efficiency.
        """
        return {key: self[key] for key in keys}

    def __setitem__(self, key: str, value: object) -> None:
        """
        Sets the ("parsed", i.e. raw python) value stored under key.
        Note that if the data source stores input data, this function makes no sense.
        """
        if not self._check_key(key):
            raise KeyError("Data source does not support storing this key")
        if self.stores_input_data or self.read_only:
            raise TypeError("Data source does not support storing parsed data")
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
        an error message string. It must not throw an exception.
        The default = "" behaviour must NOT be overwritten.
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
        Sets several inputs at once. input is a dict {key, vals}
        """
        for key, val in key_vals.items():
            self.set_input(key, val)

    def __str__(self) -> str:
        return "Data source of type " + self.dict_type + ": " + self.description


class CharDataSourceDict(CharDataSource):
    """
    Wrapper dicts (one for input data / one for parsed) -> CharDataSource. Used for testing.
    """
    dict_type = "Char data source dict"
    stores_input_data = True
    stores_parsed_data = True

    def __init__(self):
        self.input_data = dict()
        self.parsed_data = dict()