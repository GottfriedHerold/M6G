from .CharVersionConfig import CVConfig, BaseCVManager
from typing import Iterable, TYPE_CHECKING
if TYPE_CHECKING:
    from .DataSourceBase import CharDataSourceBase

def test_cv_config():

    class TestCVManager(BaseCVManager):

        log = list()  # we let our Managers append to the log to test that its functions are called in the correct order.
        id: int

        def make_append_log(self, x):
            def fun(arg):
                type(self).log.append((x, arg))
                return arg
            return fun

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.id = self.kwargs['id']
            self.log.append(self.id)

        def post_setup(self):
            if self.id == 2:
                self.cv_config.add_to_end_of_post_process_queue(self.make_append_log(102))
            else:
                self.cv_config.add_to_front_of_post_process_queue(self.make_append_log(100+self.id))
            self.log.append(1000+self.id)

            # so we have 101 -> 101,102 _> 103,101,102

        def validate_config(self):
            if self.id == 1:
                self.log.append(50)

        def get_data_sources(self) -> Iterable['CharDataSourceBase']:
            if self.id == 2:
                self.cv_config.add_to_front_of_post_process_queue(lambda l: l+[10])
                self.cv_config.add_to_front_of_post_process_queue(self.make_append_log(1000))
            return [-self.id]  # wrong type is intended for now. We don't actually use a data source.



    CVConfig.register('test_cv', TestCVManager)

    recipe1 = {
        'edit_mode': True,
        'data_sources': [
            {'type': 'test_cv', 'kwargs': {'id': 1}},
            {'type': 'test_cv', 'kwargs': {'id': 2}},
            {'type': 'test_cv', 'kwargs': {'id': 3}},
        ],
    }

    CVConfig.validate_syntax(recipe1)

    cvc1 = CVConfig(from_python=recipe1, setup_managers=False, validate_setup=False)
    js = cvc1.json_recipe
    assert js
    cvc2 = CVConfig(from_json=js, setup_managers=False, validate_setup=False)
    assert cvc2.python_recipe == recipe1
    assert TestCVManager.log == []
    cvc = CVConfig(from_python=recipe1)
    assert TestCVManager.log == [
        1, 2, 3,  # from setup
        1001, 1002, 1003,  # from post_setup
        (103, None), (101, None), (102, None),  # post_setups post-processing queue
        50,  # validate_setup
    ]
    TestCVManager.log = []

    sources = cvc.make_data_sources()
    assert sources == [-1, -2, -3, 10]
    assert TestCVManager.log == [(1000, [-1, -2, -3])]