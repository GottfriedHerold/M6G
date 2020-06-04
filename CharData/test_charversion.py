from . import CharVersion
from . import Parser
import logging

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

    cv.lists = [list_1, list_2, list_3, list_4, list_5, list_6, list_7]

    cv.bulk_set({'delme': 1, 'delmetoo': '2'}, target_type ='typeP')
    cv.bulk_set_input({'delmetootoo': '=2'}, where =2)

    commanddel1 = {'action': 'delete', 'target_type': 'typeP', 'keys': [ 'delme', 'delmetoo'] }
    commanddel2 = {'action': 'delete', 'where': 2, 'keys': ['delmetootoo']}
    commandadd1 = {'action': 'set', 'target_desc': 'desc_p', 'key_values': {'b.x': 5, 'bb': True}}
    commandadd2 = {'action': 'set_input', 'where': 1, 'key_values': [('b.b.x', '=$AUTO * $AUTO')]}
    commandadd3 = {'action': 'set_input', 'where': 1, 'key_values': []}

    commandget1 = {'action': 'get_input', 'where': 1, 'keys': ['b.b.x', 'b.x']}
    commandget2 = {'action': 'get_source', 'queries': ['b.b.x', 'b.x', 'x.bb', 'b.b.c.x']}
    commandget3 = {'action': 'get', 'queries': ['b.b.x', 'b.x', 'x.bb']}
    commandget4 = {'action': 'get_source', 'queries': ['b.b.c.x']}
    commandget5 = {'action': 'get', 'queries': ('b.b.d.x',)}
    commandget6 = {'action': 'get', 'queries': []}

    answer = cv.bulk_process([commandadd1, commandadd2, commandadd3, commanddel1, commanddel2, commandget1, commandget2, commandget3, commandget4, commandget5, commandget6])
    answer1 = answer['get_input']
    assert answer1 == {'b.b.x': '=$AUTO * $AUTO', 'b.x': ''}
    answer2 = answer['get_source']
    assert len(answer2) == 4
    assert answer2['b.b.x'] == ('=$AUTO * $AUTO', True)
    assert answer2['b.x'][1] is False
    assert answer2['x.bb'][1] is False
    assert isinstance(answer2['b.x'][0], (str, type(None)))
    assert isinstance(answer2['x.bb'][0], (str, type(None)))
    assert answer2['b.b.c.x'] == ('=$AUTO * $AUTO', True)
    answer3 = answer['get']
    assert answer3 == {'b.b.x':25, 'b.x': 5, 'x.bb': True, 'b.b.d.x': 25}
