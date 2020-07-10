from CharData.DataSources import CharDataSourceDict, CharDataSourceBase
from CharData import BaseCharVersion
import unittest


class TestBaseCharVersion(unittest.TestCase):

    def test_charversion_utils(self):
        list_1 = CharDataSourceDict()
        list_1.description = "desc1"
        list_1.dict_type = "typeA"
        list_2 = CharDataSourceDict()
        list_2.description = "desc2"
        list_2.dict_type = "typeA"
        list_3 = CharDataSourceDict()
        list_3.description = "desc3"
        list_3.dict_type = "typeB"
        list_4 = CharDataSourceDict()
        list_4.description = "desc4"
        list_4.dict_type = "typeB"
        list_4.default_write = True
        list_5 = CharDataSourceDict()
        list_5.description = "desc_generic"
        list_5.dict_type = "type_generic"
        list_6 = CharDataSourceDict()
        list_6.description = "desc_generic"
        list_6.dict_type = "type_generic"

        cv = BaseCharVersion.BaseCharVersion(data_sources=[list_1, list_2, list_3, list_4, list_5, list_6])
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

        class OnlyParsed(CharDataSourceBase):
            stores_input_data = False
            stores_parsed_data = True

            def __init__(self):
                self.parsed_data = dict()

        list_7 = OnlyParsed()
        list_7.description = "desc_p"
        list_7.dict_type = "typeP"

        cv.data_sources = [list_2, list_4, list_7]
        assert cv.get_data_source(target_type="typeB") is list_4

        cv.data_sources = [list_1, list_2, list_3, list_4, list_5, list_6, list_7]

        cv.bulk_set({'delme': 1, 'delmetoo': '2'}, target_type='typeP')
        cv.bulk_set_input({'delmetootoo': '=2'}, where=2)

        commanddel1 = {'action': 'delete', 'target_type': 'typeP', 'keys': ['delme', 'delmetoo'] }
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
        assert answer3 == {'b.b.x': 25, 'b.x': 5, 'x.bb': True, 'b.b.d.x': 25}
