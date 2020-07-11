"""
This file defines the CharDataSourceDict class: A simple char data source class that just wraps two dicts.
"""

from __future__ import annotations
from.CharDataSourceBase import CharDataSourceBase


class CharDataSourceDict(CharDataSourceBase):
    """
    Wrapper for dicts (one for input data / one for parsed) -> CharDataSourceBase. Used for testing only.
    """
    dict_type = "Char data source dict"
    stores_input_data = True
    stores_parsed_data = True

    def __init__(self, /):
        self.input_data = dict()
        self.parsed_data = dict()
