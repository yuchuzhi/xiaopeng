import os
import traceback 
import logging
import importlib
from cfg_parer import CfgParser


class Runner(object):
    def __init__(self):
        self.filepath = None
        self.target = None
        self.debugger_type = None
        self.board = None
        self.case = None
        self.appname = None

    def download(self, filepath):    
        return self.board.programming(filepath, target=self.target)
    
    def init(self, boardname, appname, app_target):
        cfg = CfgParser()
        self.appname = appname
        self.board = cfg.get_board(boardname)
        self.case = get_case_object(appname)(self.board)
        self.target = app_target

    def run_test(self, filepath):
        try:
            logging.info('{:#^48}'.format(f" Run Start "))
            logging.info('{:-^10}'.format(f" Run Board: {self.board.name}, App: {self.appname}, Target: {self.target}"))
            print(self.board.__dict__)
            self.case.pre_init()
            ret, output = self.download(filepath)
            logging.info(output)
            if ret == 0:
                self.case.interact()
                result = "PASS"
            else:
                result = "Download Fail"
        except Exception as e:
            traceback.print_exc()
            result = "FAIL"
        finally:
            self.case.deinit()
            logging.info('{:#^48}'.format(f" Run End "))
            return result

def get_case_object(appname):
    logging.info(f"get case object for {appname}")
    app_module = importlib.import_module(f"app_test.{appname}")
    return getattr(app_module, "Case")

