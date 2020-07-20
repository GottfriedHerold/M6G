"""
This file provides an empty BaseCharVersion that acts as a test fixture.
"""
from __future__ import annotations
# from DataSources.CharDataSourceBase import CharDataSourceBase
from DataSources.CharDataSourceDict import CharDataSourceDict
from CharData import BaseCharVersion


#Simple BaseCharVersion that is just for testing lookups and the parser.
def get_empty_base_char_version(*, number_of_data_sources=3):
    data_sources = []
    for i in range(number_of_data_sources):
        new_data_source = CharDataSourceDict()
        new_data_source.description = "D" + str(i+1)
        data_sources += [new_data_source]
    return BaseCharVersion(data_sources=data_sources)
