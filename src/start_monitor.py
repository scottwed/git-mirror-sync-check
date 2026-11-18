import os
from datetime import datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from socket import getaddrinfo, AF_INET, AF_INET6
from subprocess import run
from sys import stderr, argv
from time import sleep, monotonic
from typing import Any

from loguru import logger

from alerts import process_alert_rules
from config_manager import ConfigManager
from mirror_health import GitMirrorHealth, prepare_mirror_health_objects
from notifier_email import ENV_VARNAME_EMAIL_PASSWORD
from util import is_port_open, calc_repo_url, calc_ss_diff, validate_input_file_path

PRODUCT = 'Git Mirror Sync Check'
VERSION = '1.0'

"""
Git Mirror Sync Check - Standalone edition
To minimize maintenance, this edition will avoid requirements that require installation of
 additional services, such as a timeseries database, alert manager, and notification services.
 Instead, the script will do basic monitoring, relying upon its self-contained knowledge of each monitored
  mirror.
"""

### Don't edit this section ###
global last_primary_failure_ts
# noinspection PyRedeclaration
last_primary_failure_ts = datetime.min

### User modifiable ###
logger.remove()  # Remove all existing handlers
logger.add(stderr, level="INFO")  # Prevent debug and lower from appearing on console
LOG_FILE_PATH = "mirror_sync_check.log"  # Initialized during argument parsing

ENV_VARNAME_MSC_GIT_PATH = 'MSC_GIT_PATH'
GIT_PATH = os.environ.get(ENV_VARNAME_MSC_GIT_PATH, r'C:\Program Files\Git\cmd\git.exe')
# GIT_PATH = os.environ.get("MSC_GIT_PATH", r'/usr/bin/git')

PRIMARY_FAILURE_PAUSE_SECS = 30  # 30 second default

@logger.catch(reraise=True)
def main(cm: ConfigManager):
    # The script expects that the primary and all mirrors will have the same repo projects.
    repos_for_project: dict[str, list[GitMirrorHealth]] = dict()
    while True:
        current_in_service = get_in_service_from_dns(cm.mirror_rr_fqdn)
        loop_start = monotonic()
        logger.info('Mirrors in service: {}', current_in_service)
        for repo_path in cm.project_paths:
            prepare_mirror_health_objects(repo_path, repos_for_project, cm.primary_fqdn, cm.mirror_hosts)
            scan_repos_for_project(repo_path, repos_for_project[repo_path], current_in_service)
            process_alert_rules(repos_for_project[repo_path], cm.email_notifier)
        loop_stop = monotonic()
        average_repo_scan_duration = (loop_stop - loop_start) / len(cm.project_paths)
        logger.info("Average duration for scanning a project was {avg:.2f} seconds", avg=average_repo_scan_duration)
        sleep_seconds = int(max(0, cm.max_poll_freq_secs - (loop_stop - loop_start)))
        logger.info("Sleeping for {} seconds to comply with active scan constraint of {} seconds",
                    sleep_seconds, cm.max_poll_freq_secs)
        sleep(sleep_seconds)


def get_in_service_from_dns(mirrors_rr_fqdn: str) -> list[Any]:
    current_in_service = [a[4][0] for a in getaddrinfo(mirrors_rr_fqdn, 22, family=AF_INET)]
    current_in_service += [a[4][0] for a in getaddrinfo(mirrors_rr_fqdn, 22, family=AF_INET6)]
    current_in_service.sort(key=lambda x: (ip_address(x).version, ip_address(x)))
    return current_in_service


def scan_repos_for_project(repo_path: str, ghm_list: list[GitMirrorHealth], current_in_service: list[str]):
    global last_primary_failure_ts
    if datetime.now() < last_primary_failure_ts + timedelta(seconds=PRIMARY_FAILURE_PAUSE_SECS):
        logger.warning("Skipping poll cycle due to recent failure")
        return
    primary_ghm = ghm_list[0]
    poll_git_host(repo_path, primary_ghm, primary_ghm)
    if not primary_ghm.up:
        logger.warning("[{repo}] Aborting current polling cycle due to failure of primary", repo=repo_path)
        last_primary_failure_ts = datetime.now()
        return
    for mirror in ghm_list[1:]:
        mirror.in_service = 1 if str(mirror.ip_address) in current_in_service else 0
        poll_git_host(repo_path, mirror, primary_ghm)


def poll_git_host(repo_path: str, ghm: GitMirrorHealth, primary_ghm: GitMirrorHealth):
    header = f'{repo_path} - {ghm.role} - {ghm.ip_address}'
    ghm.git_port_open = 1
    logger.debug('[{header}] Retrieving references', header=header)
    mirror_refs = get_ref_list(calc_repo_url(str(ghm.ip_address), repo_path))

    logger.info('[{header}] Retrieved {ref_count} references.',
                header=header, ref_count=len(mirror_refs[1].split('\n')))
    logger.debug('[{header}] Refs: \n{refs}', header=header, refs=mirror_refs[1])

    if mirror_refs[2]:
        logger.error('[{header}] Failure to retrieve references. Git error: {err}',
                     header=header, err=mirror_refs[2])
        ghm.sync_errors_total += 1
        ghm.last_error_message = mirror_refs[2]
        ghm.up = 0
        ghm.git_port_open = 1 if is_port_open(str(ghm.ip_address), 9418) else 0

    else:
        ghm.up = 1
        ghm.sync_errors_total = 0
        ghm.index_snapshot = mirror_refs[1].strip()

    if ghm is primary_ghm:
        ghm.last_in_sync = datetime.now()
    else:
        if ghm.index_snapshot == primary_ghm.index_snapshot:
            ghm.in_sync = 1
            ghm.last_in_sync = primary_ghm.last_in_sync
        else:
            ghm.in_sync = 0
            discrepancy = calc_ss_diff(primary_ghm.index_snapshot, ghm.index_snapshot)
            logger.error(f"[{header}] OUT OF SYNC!\n{discrepancy}", header=header, discrepancy=discrepancy)


def get_ref_list(repo_url: str) -> tuple[int, str, str]:
    # Returns a tuple of (git exit code, ls-remote output, git error messages)
    cmd = [GIT_PATH, 'ls-remote', repo_url]
    logger.debug('Running {cmd}', cmd=' '.join(cmd))
    result = run(cmd, shell=True, capture_output=True)
    return result.returncode, result.stdout.decode('utf-8').strip(), result.stderr.decode('utf-8').strip()


def print_help():
    print(f'{PRODUCT} (standalone) version {VERSION}\n')
    print('A self-contained application to perform low-impact synchronization status monitoring of read-only git mirrors.')
    print('Current logic depends upon the execution of anonymous "git ls-remote" requests, limiting it to knowledge '
          'of git references.')
    print('It does not check for presence or integrity of objects, indexes, config, hooks, or info files.')
    print('Connection failures/refusal and discrepancies with the primary repo are captured as errors.')
    print('Upon exceeding the threshold for consecutive errors, a single report for the entire repo is emailed '
          'as an alert.')
    print('At startup, a process startup email is sent to validate SMTP settings and confirm startup time.')
    print('Modifying the log file location or 5MB * 10 rolling log settings can be revised at '
          'the top of this script.')
    print()
    print('Inputs:')
    print('Create a "repos.txt" file containing repo paths to monitor (one per line), like "bison.git" or '
          '"gnucap/gnucap-modelgen-verilog.git"')
    print('Create a "mirrors.txt" file containing the mirror\'s IPv4/6 addresses to monitor (one per line),'
          ' like "1.2.3.4" and "2a0e:97c0:3ea:82b::1"')
    print('Copy the config_example.yaml file to a new .yaml file, and update each entry using a text editor '
          'including the relative or full path for the two input .txt files. ')
    print('Note: Lines starting with # are ignored in the.txt and .yaml files')
    print()
    print("Usage:")
    print('python (or uv run) msc_config.yaml [--debug]')
    print(f'If the SMTP server requires a password, set environment variable: {ENV_VARNAME_EMAIL_PASSWORD} '
           'before running the script')
    print('If the git executable is not present in the user\'s executable path, '
          f'set environment variable {ENV_VARNAME_MSC_GIT_PATH}')


def load_monitor_config(config_file: str):
    config_path = Path(config_file)
    invalid_message = validate_input_file_path(config_path)
    if invalid_message:
        logger.error('Configuration {}  Exiting for safety.')
        exit(2)

    config_mgr = ConfigManager(config_path)
    if config_mgr.problems:
        for problem in config_mgr.problems:
            logger.error('Initialization error: {}', problem)
        exit(3)
    return config_mgr


if __name__ == '__main__':
    my_repo_paths: list[str] = []
    if '-v' in argv or '--version' in argv:
        print(f'{PRODUCT} (standalone) version {VERSION}\n')
        exit(0)

    if '--debug' in argv:
        argv.remove('--debug')
        logger.info("File logger will include debug level messages.")
        logger.add(LOG_FILE_PATH, rotation="5 MB", retention=10, level="DEBUG")
    else:
        logger.add(LOG_FILE_PATH, rotation="5 MB", retention=10, level="INFO")

    if len(argv) != 2 or argv[1] in ('-h', '--help'):
        print_help()
        exit(1)
    logger.info('Loading configuration data from: {}', argv[1])
    my_config_mgr = load_monitor_config(argv[1])

    # Send a test email at startup
    logger.info("Attempting to send startup email notification.")
    my_config_mgr.email_notifier.send(subject=f"{PRODUCT} startup", body=f"{PRODUCT} {VERSION} script has been started")
    main(my_config_mgr)
