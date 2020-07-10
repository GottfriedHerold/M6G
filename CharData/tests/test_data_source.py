from CharData.DataSources import CharDataSourceDict, CharDataSourceBase
from CharData import Parser
import unittest

def _test_dict_like_data_source(data_source: CharDataSourceBase):
    assert "x" not in data_source
    assert data_source.contains_unrestricted or data_source.contains_restricted
    assert data_source.stores_parsed_data or data_source.stores_input_data
    assert not data_source.read_only
    if data_source.default_write:
        assert data_source.type_unique
    assert "__x__" not in data_source
    if data_source.contains_unrestricted:
        test_key = "x.y"
        test_key2 = "x.y.z"
    else:
        test_key = "__x__.y"
        test_key2 = "__x__.y.z"

    if data_source.stores_input_data:
        data_source.set_input(test_key, "12")
        assert data_source.get_input(test_key) == "12"
        assert data_source[test_key] == 12
        assert test_key in data_source
        data_source.set_input(test_key, "=1+2")
        assert data_source.get_input(test_key) == "=1+2"
        assert isinstance(data_source[test_key], Parser.AST)
        data_source.set_input(test_key, "'abc")
        assert data_source.get_input(test_key) == "'abc"
        assert data_source[test_key] == "abc"
        data_source.bulk_set_inputs({test_key: "3", test_key2: "'4"})
        assert data_source.bulk_get_inputs((test_key, test_key2)) == {test_key: "3", test_key2: "'4"}
        assert data_source.bulk_get_items((test_key, test_key2)) == {test_key: 3, test_key2: "4"}

        data_source.set_input(test_key, "")
        assert test_key not in data_source
        data_source.set_input(test_key, "")
        assert test_key not in data_source

        data_source.set_input(test_key, "1")
        assert test_key in data_source
        del data_source[test_key]
        assert test_key not in data_source
    else:
        test_key += ".z"
        assert test_key not in data_source
        data_source[test_key] = "=a"
        assert data_source[test_key] == "=a"
        data_source.get_input(test_key)  # Just verifies that this does not raise an exception
        data_source[test_key] = 1
        assert data_source[test_key] == 1
        del data_source[test_key]
        assert test_key not in data_source
        data_source.bulk_set_items({test_key: 5, test_key2: "6"})
        assert data_source.bulk_get_items((test_key, test_key2)) == {test_key: 5, test_key2: "6"}


class TestCharDataSourceDict(unittest.TestCase):

    class OnlyParsed(CharDataSourceBase):
        stores_input_data = False
        stores_parsed_data = True
        def __init__(self):
            self.parsed_data = dict()

    class OnlyInput(CharDataSourceBase):
        stores_input_data = True
        stores_parsed_data = False
        def __init__(self):
            self.input_data = dict()

    def test_data_source_dict(self):
        x = CharDataSourceDict()
        _test_dict_like_data_source(x)

    def test_only_parsed(self):
        x = self.OnlyParsed()
        _test_dict_like_data_source(x)

    def test_only_inpunt(self):
        x = self.OnlyInput()
        _test_dict_like_data_source(x)
