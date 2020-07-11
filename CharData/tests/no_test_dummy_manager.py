"""
Defines a DummyManager and tests that the corresponding functions get called.
"""

from __future__ import annotations

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
            self.cv_config.add_to_front_of_post_process_queue(self.make_append_log(100 + self.id))
        self.log.append(1000 + self.id)

        # so we have 101 -> 101,102 _> 103,101,102

    def validate_config(self):
        if self.id == 1:
            self.log.append(50)

    def get_data_sources(self) -> Iterable['CharDataSourceBase']:
        if self.id == 2:
            self.cv_config.add_to_front_of_post_process_queue(lambda l: l + [10])
            self.cv_config.add_to_front_of_post_process_queue(self.make_append_log(1000))
        return [-self.id]  # wrong type is intended for now. We don't actually use a data source.

