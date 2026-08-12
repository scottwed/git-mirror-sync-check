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
from notifier_email import EmailSender, ENV_VARNAME_EMAIL_PASSWORD
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

# Note: Git remote ports - 22 SSH, 80 HTTP, 443 HTTPS, 9418 GIT R/O anon

### Don't edit this section ###
global last_primary_failure_ts
# noinspection PyRedeclaration
last_primary_failure_ts = datetime.min

### User modifiable ###
logger.remove()  # Remove all existing handlers
logger.add(stderr, level="INFO")  # Prevent debug and lower from appearing on console
logger.add("mirror_sync_check.log", rotation="5 MB", retention=10)  # Write detailed logs with rotation

GIT_PATH = os.environ.get("MSC_GIT_PATH", r'C:\Program Files\Git\cmd\git.exe')
# GIT_PATH = os.environ.get("MSC_GIT_PATH", r'/usr/bin/git')

PRIMARY_FAILURE_PAUSE_SECS = 30  # 30 second default
active_scan_interval_secs = 60 * 5  # 5 minutes default
inactive_scan_interval_secs = 60 * 60 * 12  # 12 hour default

@logger.catch(reraise=True)
def main(repo_paths: list[str], primary_fqdn: str, mirrors_rr_fqdn: str,
         mirror_hosts: list[str], notifier: EmailSender):
    repos_for_project: dict[str, list[GitMirrorHealth]] = dict()
    while True:
        # The script assumes that the primary and all mirrors should have copy of each git repo.
        current_in_service = get_in_service_from_dns(mirrors_rr_fqdn)
        loop_start = monotonic()
        logger.info('Mirrors in service: {}', current_in_service)
        for repo_path in repo_paths:
            prepare_mirror_health_objects(repo_path, repos_for_project, primary_fqdn, mirror_hosts)
            scan_repos_for_project(repo_path, repos_for_project[repo_path], current_in_service)
            process_alert_rules(repos_for_project[repo_path], notifier)
        # sleep(30)  # TODO Implement per-repo scan delay logic
        loop_stop = monotonic()
        average_repo_scan_duration = (loop_stop - loop_start) / len(repo_paths)
        logger.info("Average duration for scanning a project was {avg:.2f} seconds", avg=average_repo_scan_duration)
        sleep_seconds = int(max(0, active_scan_interval_secs - (loop_stop - loop_start)))
        logger.info("Sleeping for {} seconds to comply with active scan constraint of {} seconds",
                    sleep_seconds, active_scan_interval_secs)
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
    # logger.debug('[{header}] Refs: \n{refs}', header=header, refs=mirror_refs[1])

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
    # logger.info('Running {cmd}', cmd=' '.join(cmd))
    result = run(cmd, shell=True, capture_output=True)
    return result.returncode, result.stdout.decode('utf-8').strip(), result.stderr.decode('utf-8').strip()


def print_help():
    print(f'{PRODUCT} (standalone) version {VERSION}\n')
    print(f'A self-contained application to perform low-impact synchronization status monitoring of git mirrors.')
    print(f'Current logic depends upon the execution of anonymous "git ls-remote" requests, limiting it to knowledge '
          f'of git references.')
    print(f'It does not check for presence or integrity of objects, indexes, config, hooks, or info files.')
    print(f'Connection failures/refusal and discrepancies with the primary repo are captured as errors.')
    print(f'Upon exceeding the threshold for consecutive errors, a single report for the entire repo is emailed '
          f'as an alert.')
    print(f'At startup, a process startup email is sent to validate SMTP settings and confirm startup time.')
    print(f'Modifying the log file location or 5MB * 10 rolling log settings can be revised at '
          f'the top of this script.')
    print()
    print(f'Inputs:')
    print(f'Create a "repos.txt" file containing repo paths to monitor (one per line), like "bison.git" or '
          f'"gnucap/gnucap-modelgen-verilog.git"')
    print(f'Create a "mirrors.txt" file containing the mirror\'s IPv4/6 addresses to monitor (one per line),'
          f' like "1.2.3.4" and "2a0e:97c0:3ea:82b::1"')
    print(f'Copy the config_example.yaml file to a new .yaml file, and update each entry using a text editor '
          f'including the relative or full paths to the two input .txt files. ')
    print(f'Note: Lines starting with # are ignored in the.txt and .yaml files')
    print()
    print("Usage:")
    print(f'python (or uv run) my_msc_config.yaml')
    print(f'If the SMTP server requires a password, set environment variable: {ENV_VARNAME_EMAIL_PASSWORD} '
          f'before running the script')


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
    if len(argv) <= 1:
        print_help()
        exit(1)
    logger.info('Loading configuration data from: {}', argv[1])
    my_config_mgr = load_monitor_config(argv[1])

    # Send a test email at startup
    mailer = EmailSender(argv[1])
    mailer.send(subject=f"{PRODUCT} startup", body=f"{PRODUCT} {VERSION} script has been started")
    main(my_config_mgr)

    # main(repo_paths=my_repo_paths, primary_fqdn=my_primary_repo_fqdn,
    #      mirrors_rr_fqdn=my_mirrors_rr_fqdn, mirror_hosts=my_mirror_hosts,
    #      notifier=mailer)
