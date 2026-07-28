import os
from datetime import datetime
from ipaddress import ip_address
from socket import gethostbyname, getaddrinfo, AF_INET, AF_INET6
from subprocess import run
from sys import exit, stderr
from time import sleep
from typing import Any

from loguru import logger

from mirror_health import GitMirrorHealth, MirrorRole, push_to_victoria_metrics, render_prometheus
from util import is_port_open, calc_repo_url


"""
GIT Mirror Sync Check - Standalone edition
To minimize ongoing maintenance, this edition will avoid requirements that require installation of
 additional services, such as a timeseries database, alert management, and notification services.
 Instead, the script will do basic monitoring, relying upon its self-managed knowledge of each monitored
  mirror.
"""

logger.remove()  # Remove all existing handlers
logger.add(stderr, level="INFO")  # Prevent debug and lower from appearing on console
logger.add("mirror_sync_check.log", rotation="5 MB", retention=10)  # Write detailed logs with rotation

GIT_PATH = os.environ.get("MSC_GIT_PATH", r'C:\Program Files\Git\cmd\git.exe')
# GIT_PATH = os.environ.get("MSC_GIT_PATH", r'/usr/bin/git')

primary_failure_pause_secs = 30             # 30 second default
active_scan_interval_secs = 60 * 5          # 5 minutes default
inactive_scan_interval_secs = 60 * 60 * 12  # 12 hour default

repo_rr_record: str = 'git.git.savannah.gnu.org'
primary_repo: str = 'git.savannah.gnu.org'
primary_repo_addr: str = gethostbyname(primary_repo)

tier_3_mirrors: list[str] = ['15.204.9.231', '15.204.88.113', '51.255.194.124', '92.118.206.28',
                             '135.148.138.35', '176.100.37.192', '176.100.37.193', '178.104.15.118',
                             '185.112.147.164',
                             # '2001:470:415d:1000:5054:ff:fe8d:c1a3', '2001:41d0:305:2100::1:64b',
                             # '2604:2dc0:101:200::1c35', '2604:2dc0:202:300::5d3', '2604:2dc0:202:300::a52',
                             # '2a01:4f8:1c19:4eae::1', '2a0e:97c0:3ea:528::1', '2a0e:97c0:3ea:52a::1',
                             # '2a0e:97c0:3ea:82b::1',
                             ]

# Git remote ports - 22 SSH, 80 HTTP, 443 HTTPS, 9418 GIT R/O anon

# TODO implement a snapshot history (last 5-10 snapshot hashes) to estimate the staleness of the mirror.
# TODO write alert logic.  Alert on up=0 for > x minutes, git_port_open=0 > x minutes, in_service=0 > 26 hours
# TODO Isolate port_open check from project-level checking.

def main(repo_paths:list[str]):
    if not (primary_repo and tier_3_mirrors and repo_paths):
        logger.error("Missing one or more required inputs!")
        exit(1)

    repos_for_project: dict[str, list[GitMirrorHealth]] = dict()
    current_in_service = [a[4][0] for a in getaddrinfo(repo_rr_record, 22, family=AF_INET)]
    current_in_service += [a[4][0] for a in getaddrinfo(repo_rr_record, 22, family=AF_INET6)]
    current_in_service.sort(key=lambda x: (ip_address(x).version, ip_address(x)))
    logger.info('In service: {}', current_in_service)

    while True:
        # The script assumes that the primary and all mirrors should have copy of each git repo.
        for repo_path in repo_paths:
            primary_health = prepare_mirror_health_objects(repo_path, repos_for_project)

            logger.info("[{repo}] Retrieving references from primary: ({primary})", repo=repo_path,
                        primary=primary_repo)
            primary_health.git_port_open = 1 if is_port_open(str(primary_health.ip_address), 9418) else 0
            primary_refs = get_ref_list(calc_repo_url(primary_repo, repo_path))
            print()
            if primary_refs[2]:
                logger.error("[{repo}] Failure to retrieve references from primary. Git error: {err}", repo=repo_path,
                             err=primary_refs[2])
                primary_health.last_error_message = primary_refs[2]
                primary_health.sync_errors_total += 1
                logger.info("[{repo}] Pausing all monitoring for {delay} seconds", repo=repo_path, delay=retry_delay_secs)
                sleep(retry_delay_secs)
                continue
            logger.info('[{repo}] Retrieved {ref_count} references from primary.',
                        repo=repo_path, ref_count=len(primary_refs[1].split('\n')))
            logger.debug('[{repo}] Refs: \n{refs}', repo=repo_path, refs=primary_refs[1])
            primary_health.index_snapshot = primary_refs[1].strip()
            primary_health.up = 1
            primary_health.last_in_sync = datetime.now()

            for mirror in repos_for_project[repo_path][1:]:
                poll_git_host(current_in_service, mirror, primary_health, repo_path)

            # print(render_prometheus(repos_for_project[repo_path]))
        # TODO Implement per-repo scan delay logic
        # sleep(30)
        # sleep(active_scan_interval_secs)  # FIXME Enable this for prod


def poll_git_host(current_in_service: list[Any], mirror: GitMirrorHealth, primary_health: GitMirrorHealth,
                  repo_path: str):
    mirror.git_port_open = 1 if is_port_open(str(mirror.ip_address), 9418) else 0
    mirror.in_service = 1 if str(mirror.ip_address) in current_in_service else 0
    logger.info('[{repo}] Retrieving references for mirror: {mirror} ({ip})', repo=repo_path,
                mirror=mirror.instance, ip=mirror.ip_address)
    mirror_refs = get_ref_list(calc_repo_url(str(mirror.ip_address), repo_path))

    logger.info('[{repo}] Retrieved {ref_count} references from mirror.', repo=repo_path,
                ref_count=len(mirror_refs[1].split('\n')))
    logger.debug('[{repo}] Refs: \n{refs}', repo=repo_path, refs=mirror_refs[1])

    if mirror_refs[2]:
        logger.error('[{repo}] Failure to retrieve references from mirror. Git error: {err}',
                     repo=repo_path, err=mirror_refs[2])
        mirror.sync_errors_total += 1
        mirror.last_error_message = mirror_refs[2]
        if "unable to connect" in mirror_refs[2]:
            mirror.up = 0
        # Exit code 128: Valid git CLI syntax was used, but the remote server didn't respond.
        # Exit code 128: If .git/packed-refs is intentionally corrupted.
    else:
        mirror.up = 1
        mirror.index_snapshot = mirror_refs[1].strip()

    if mirror.index_snapshot == primary_health.index_snapshot:
        mirror.in_sync = 1
        mirror.last_in_sync = primary_health.last_in_sync
    else:
        mirror.in_sync = 0
        logger.error("[{repo}] OUT OF SYNC! on {mirror}", repo=repo_path, mirror=mirror.instance)


def prepare_mirror_health_objects(repo_path: str, repos_for_project: dict[str, list[GitMirrorHealth]]) -> GitMirrorHealth:
    # On-demand initialization of the mirror health instances.
    # First item in the list will be the primary, followed by all the mirrors.
    if repo_path not in repos_for_project:
        primary_health = GitMirrorHealth(
            project=repo_path, instance=primary_repo, ip_address=ip_address(primary_repo_addr),
            role=MirrorRole.primary, up=0, in_service=1, in_sync=1,
            last_in_sync=datetime.now(), sync_errors_total=0, last_error_message="",
            index_snapshot=""
        )
        repos_for_project[repo_path] = [primary_health]
        # Create placeholders for all the mirrors
        for mirror in tier_3_mirrors:
            mh = GitMirrorHealth(
                project=repo_path, instance=mirror, ip_address=ip_address(mirror),
                role=MirrorRole.tertiary, up=0, in_service=1, in_sync=0,
                last_in_sync=datetime.min, sync_errors_total=0, last_error_message="",
                index_snapshot="")
            repos_for_project[repo_path].append(mh)

    else:
        primary_health = repos_for_project[repo_path][0]
    return primary_health


def get_ref_list(repo_url: str) -> tuple[int, str, str]:
    # Returns a tuple of (git exit code, ls-remote output, git error messages)
    cmd = [GIT_PATH, 'ls-remote', repo_url]
    logger.info('Running {cmd}', cmd=' '.join(cmd))
    result = run(cmd, shell=True, capture_output=True)
    return result.returncode, result.stdout.decode('utf-8').strip(), result.stderr.decode('utf-8').strip()


if __name__ == '__main__':
    with open('one_repo.txt', 'r', encoding='utf-8') as f:
        repo_paths = [l.strip() for l in f.readlines() if l.strip()]
    print(repo_paths)
    main(repo_paths)
