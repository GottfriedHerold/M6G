import pytest

import CharData.DataSources
from . import BaseCharVersion

#Simple BaseCharVersion that is just for testing lookups and the parser.
@pytest.fixture(scope='function')
def empty3cv():
    DataSet1 = CharData.DataSources.CharDataSourceDict()
    DataSet1.description = "D1"
    DataSet2 = CharData.DataSources.CharDataSourceDict()
    DataSet2.description = "D2"
    DataSet3 = CharData.DataSources.CharDataSourceDict()
    DataSet3.description = "D3"

    # DataSet1 = BaseCharVersion.UserDataSet()
    # DataSet2 = BaseCharVersion.UserDataSet()
    # DataSet3 = BaseCharVersion.CoreRuleDataSet()
    return BaseCharVersion.BaseCharVersion(data_sources=[DataSet1, DataSet2, DataSet3])
