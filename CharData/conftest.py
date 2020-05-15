import pytest

from . import CharVersion

#Simple CharVersion that is just for testing lookups and the parser.
@pytest.fixture(scope='function')
def empty3cv():
    DataSet1 = CharVersion.CharDataSourceDict()
    DataSet1.description = "D1"
    DataSet2 = CharVersion.CharDataSourceDict()
    DataSet2.description = "D2"
    DataSet3 = CharVersion.CharDataSourceDict()
    DataSet3.description = "D3"

    # DataSet1 = CharVersion.UserDataSet()
    # DataSet2 = CharVersion.UserDataSet()
    # DataSet3 = CharVersion.CoreRuleDataSet()
    return CharVersion.CharVersion(initial_lists=[DataSet1, DataSet2, DataSet3])
