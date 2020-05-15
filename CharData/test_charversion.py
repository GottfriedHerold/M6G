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
        data_source.get_input(test_key)  # Just verifies that this does not raise an exception
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

    x = OnlyParsed()
    _test_dict_like_data_source(x)

    class OnlyInput(CharVersion.CharDataSource):
        stores_input_data = True
        stores_parsed_data = False

        def __init__(self):
            self.input_data = dict()

    x = OnlyInput()
    _test_dict_like_data_source(x)

def test_charversion_utils():
    list_1 = CharVersion.CharDataSourceDict()
    list_1.description = "desc1"
    list_1.dict_type = "typeA"
    list_2 = CharVersion.CharDataSourceDict()
    list_2.description = "desc2"
    list_2.dict_type = "typeA"
    list_3 = CharVersion.CharDataSourceDict()
    list_3.description = "desc3"
    list_3.dict_type = "typeB"
    list_4 = CharVersion.CharDataSourceDict()
    list_4.description = "desc4"
    list_4.dict_type = "typeB"
    list_4.default_write = True
    list_5 = CharVersion.CharDataSourceDict()
    list_5.description = "desc_generic"
    list_5.dict_type = "type_generic"
    list_6 = CharVersion.CharDataSourceDict()
    list_6.description = "desc_generic"
    list_6.dict_type = "type_generic"

    cv = CharVersion.CharVersion(initial_lists=[list_1, list_2, list_3, list_4, list_5, list_6])
    assert cv.get_data_source(target_desc="desc1") is list_1
    assert cv.get_data_source(target_desc="desc2") is list_2
    assert cv.get_data_source(target_desc="desc_generic") is list_5
    assert cv.get_data_source(target_desc="desc_generic", target_type="type_generic") is list_5
    assert cv.get_data_source(target_type="typeB") is list_3
    assert cv.get_data_source() is list_4

    cv.set_input("x", "1")
    assert list_4["x"] == 1
    cv.set_input("y", "2", target_type="typeB")
    assert list_3["y"] == 2

    class OnlyParsed(CharVersion.CharDataSource):
        stores_input_data = False
        stores_parsed_data = True

        def __init__(self):
            self.parsed_data = dict()

    list_7 = OnlyParsed()
    list_7.description = "desc_p"
    list_7.dict_type = "typeP"

    cv.lists = [list_2, list_4, list_7]
    assert cv.get_data_source(target_type="typeB") is list_4
