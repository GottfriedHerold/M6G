import pytest

from . import CharVersion

# Simple CharVersion that is just for testing lookups and the parser.
@pytest.fixture
def empty3cv():
    DataSet1 = CharVersion.UserDataSet()
    DataSet2 = CharVersion.UserDataSet()
    DataSet3 = CharVersion.UserDataSet()
    return CharVersion.CharVersion(initial_lists=[DataSet1, DataSet2, DataSet3])