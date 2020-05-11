from . import CharVersion
from . import Parser

def _test_dict_like_data_source(data_source: CharVersion.CharDataSource):
    assert "x" not in data_source
    assert data_source.contains_unrestricted or data_source.contains_restricted
    assert data_source.stores_parsed_data or data_source.stores_input_data
    assert not data_source.read_only
    if data_source.default_write:
        assert data_source.type_unique
    assert "__x__" not in data_source
    if data_source.contains_unrestricted:
        test_key = "x.y"
    else:
        test_key = "__x__.y"

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
        try:
            data_source.get_input(test_key)
        except Exception:
            assert False
        data_source[test_key] = 1
        assert data_source[test_key] == 1
        del data_source[test_key]
        assert test_key not in data_source

def test_data_source_dict():
    x = CharVersion.CharDataSourceDict()
    _test_dict_like_data_source(x)
    class OnlyParsed(CharVersion.CharDataSource):
        stores_input_data = False
        stores_parsed_data = True
        def __init__(self):
            self.parsed_data = dict()

    class OnlyInput(CharVersion.CharDataSource):
        stores_input_data = True
        stores_parsed_data = False
        def __init__(self):
            self.input_data = dict()

    x = OnlyParsed()
    _test_dict_like_data_source(x)

    x = OnlyInput()
    _test_dict_like_data_source(x)