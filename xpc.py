import sys
import os
import re
import logging
import argparse
import pathlib
from zipfile import ZipFile
from cfg_parer import CfgParser
from executer import Executer
from runner import Runner
from builder import Builder
from mcutool.compilers.result import Result
from mcutool.projects_scanner import find_projects
from settings import APP_TEST_PATH, LOCAL_SCRIPT



def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-id', help='job id')
    parser.add_argument('--platform', help='specific platform when debug run task')
    parser.add_argument('--target', default="release", help='specific build target')
    parser.add_argument('--apps', default="hello_world,rtc_example", help='specific build target')
    parser.add_argument('--prjname', default="hello_world", help='specific prjname')
    parser.add_argument('--sdk', help='specific sdk package path')
    parser.add_argument('--build', action='store_true', help='build this case')
    parser.add_argument('--run', action='store_true', help='run this case')
    parser.add_argument('--task_type', default="1", help='specific task type(0: build only,1: build and run,2: run only)')
    parser.add_argument('--flash', action='store_true', help='fetch binary from server then flash it to board')
    parser.add_argument('--filepath', help='specify the elf file path for run only test.')

    return parser.parse_args()

def get_projects(sdk_root_path, applist):
    projects, count = find_projects(sdk_root_path)
    expect_prjs = {}

    for idename, project_list in projects.items():
        expect_prjs[idename] = [p for p in project_list if p.name in applist]

    return expect_prjs

def get_boardname(sdk_path, project_path):
    boardname = re.findall(f"{sdk_path}/boards/(\w+)", project_path.replace("\\", "/"))[0]
    return boardname

def run_test(filepath, boardname, appname, target):
    runner = Runner()
    runner.init(boardname, appname, target)
    ret = runner.run_test(filepath)
    ret_value = 0
    if "pass" == ret.lower():
        logging.info('{:-^48}'.format(f" Test result =  {ret} "))
    else:
        logging.error('{:-^48}'.format(f" Test result =  {ret} "))
        ret_value = 1

    return ret_value

def build_test(projects, targets, workspace):
    results = []
    output_files = []
    for idename, project in projects.items():
        for prj in project:
            for target in targets:
                builder = Builder()
                output_store_path = f"{APP_TEST_PATH}/{prj.boardname}/"
                if not os.path.exists(output_store_path):
                    os.makedirs(output_store_path)

                builder.init(idename, target, output_store_path, workspace, prj.name)
                builder.compiler.Project = prj

                result = builder.build()
                ret_value = result.result.value

                results.append(ret_value)
                if ret_value == 0:
                    build_output_file = builder.post_build(result)
                    output_files.append((build_output_file, prj.boardname, prj.name, target))
                    logging.info('{:-^48}'.format(f" Test result =  {result.result.name} "))
                else:
                    logging.error('{:-^48}'.format(f" Test result =  {result.result.name} "))

    total = len(results)
    counter_fail = 0
    counter_warnning = 0
    counter_pass = 0
    for value in results:
        if value == 0:
            counter_pass += 1
        elif value == 2:
            counter_warnning += 1
        else:
            counter_fail += 1

    logging.info(f"Total build: {total}")
    logging.info(f"Build Passes: {counter_pass}")
    logging.info(f"Build Warnnings: {counter_warnning}")
    logging.info(f"Build Fails: {counter_fail}")

    ret = 1
    if counter_fail == 0:
        ret = 0

    return ret, output_files

def build_run_test(sdk_path, apps, targets, workspace):
    sdk_path = sdk_path.replace("\\", "/")
    projects = get_projects(sdk_path, apps)
    run_results = []

    ret, output_files = build_test(projects, targets, workspace)
    for outputfile in  output_files:
        run_result = run_test(*outputfile)
        run_results.append(run_result)

    total = len(run_results)
    counter_fail = 0
    counter_pass = 0
    for value in run_results:
        if value.lower() == "pass":
            counter_pass += 1
        else:
            counter_fail += 1

    logging.info(f"Total Run: {total}")
    logging.info(f"Run Passes: {counter_pass}")
    logging.info(f"Run Fails: {counter_fail}")

    ret = 1
    if counter_fail == 0:
        ret = 0

    return ret

def download_package(rpath, lpath):
    pass

def extract(filepath, dest_path):
    if filepath.endswith(".zip"):
        zipFile = ZipFile(filepath, "r")
        for file in zipFile.namelist():
            zipFile.extract(file, dest_path)
        zipFile.close()

def main():
    if sys.version_info[0] < 3:
        print("require python >= 3.6")
        exit(1)
    
    cfg = CfgParser()
    
    args_input = get_arguments()
    workspace = pathlib.Path(LOCAL_SCRIPT).joinpath(f".workspaces/{args_input.id}").as_posix()
    log_path = pathlib.Path(workspace).joinpath("logs").as_posix()
    if not os.path.exists(workspace):
        os.makedirs(workspace)
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    
    log_file = f"{workspace}/logs/test_log.log"
    cfg.init_log(log_file)
    sdk_store_path = cfg.get_sdk_rootpath().replace("\\", "/")
    sdk_local_path = args_input.sdk
    if args_input.sdk.startswith("http://") or not args_input.sdk.startswith("https://"):
        fname = os.path.basename(args_input.sdk)
        sdk_local_path = f"{LOCAL_SCRIPT}/downloads/{fname}"
        download_package(args_input.sdk, sdk_local_path)
    
    #extract(sdk_local_path, sdk_store_path)
    targets = args_input.target.split(",")
    target = targets[0]
    apps = args_input.apps.split(",")

    task_type = int(args_input.task_type)
    if 0 == task_type:
        projects = get_projects(sdk_store_path, apps)
        ret, outputs = build_test(projects, targets, workspace)
        os._exit(ret)
    
    elif 2 == task_type:
        #args_input.filepath = "C:/MyDoc/python-study/xiaopeng/app_test/lpcxpresso55s28/hello_world_release/lpcxpresso55s28_hello_world.axf"
        ret = run_test(args_input.filepath, "lpcxpresso55s28", "hello_world", "debug")
        os._exit(ret)
    else:
        build_run_test(sdk_store_path, apps, targets, workspace)


if __name__ == "__main__":
    main()
