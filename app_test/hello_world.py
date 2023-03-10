
from .demo_apps import AppTest


class Case(AppTest):
    def __init__(self, board_obj, *args, **kwargs):
        super().__init__(board_obj, *args, **kwargs)
        self.expectedPatterns = ["hello world"]

    def interact(self):
        super().interact()
        self.spawn.write("~!@$%^&*")
        self.spawn.test_expect(["~!@$%^&*"], timeout=self.timeout)   
