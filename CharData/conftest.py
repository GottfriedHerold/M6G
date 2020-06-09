import pytest

from . import BaseCharVersion

#Simple BaseCharVersion that is just for testing lookups and the parser.
@pytest.fixture(scope='function')
def empty3cv():
    DataSet1 = BaseCharVersion.CharDataSourceDict()
    DataSet1.description = "D1"
    DataSet2 = BaseCharVersion.CharDataSourceDict()
    DataSet2.description = "D2"
    DataSet3 = BaseCharVersion.CharDataSourceDict()
    DataSet3.description = "D3"

    # DataSet1 = BaseCharVersion.UserDataSet()
    # DataSet2 = BaseCharVersion.UserDataSet()
    # DataSet3 = BaseCharVersion.CoreRuleDataSet()
    return BaseCharVersion.BaseCharVersion(initial_lists=[DataSet1, DataSet2, DataSet3])
