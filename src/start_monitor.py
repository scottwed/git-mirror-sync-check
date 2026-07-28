import os
from datetime import datetime
from ipaddress import ip_address
from socket import gethostbyname, getaddrinfo, AF_INET, AF_INET6
from subprocess import run
from sys import exit, stderr
from time import sleep

from loguru import logger

from mirror_health import GitMirrorHealth, MirrorRole, push_to_victoria_metrics, render_prometheus
from util import is_port_open, calc_repo_url

logger.remove()  # Remove all existing handlers
logger.add(stderr, level="INFO")  # Prevent debug and lower from appearing on console
logger.add("mirror_sync_check.log", rotation="5 MB", retention=10)  # Write detailed logs with rotation

retry_delay_secs = 30
GIT_PATH = os.environ.get("CGR_GIT_PATH", r'C:\Program Files\Git\cmd\git.exe')
VICTORIA_PROM_IMPORT_URL = os.environ.get("CGR_VIC_PROM_INPUT_URL",
                                          r'http://127.0.0.1:8428/api/v1/import/prometheus')

primary_repo: str = 'git.savannah.gnu.org'
primary_repo_addr: str = gethostbyname(primary_repo)
repo_rr_record: str = 'git.git.savannah.gnu.org'

tier_3_mirrors: list[str] = ['15.204.9.231', '15.204.88.113', '51.255.194.124', '92.118.206.28',
                             '135.148.138.35', '176.100.37.192', '176.100.37.193', '178.104.15.118',
                             '185.112.147.164',
                             # '2001:470:415d:1000:5054:ff:fe8d:c1a3', '2001:41d0:305:2100::1:64b',
                             # '2604:2dc0:101:200::1c35', '2604:2dc0:202:300::5d3', '2604:2dc0:202:300::a52',
                             # '2a01:4f8:1c19:4eae::1', '2a0e:97c0:3ea:528::1', '2a0e:97c0:3ea:52a::1',
                             # '2a0e:97c0:3ea:82b::1',
                             ]

# tier_3_mirrors: list[str] = ['92.118.206.28', '5.5.5.5', '15.204.88.113']
# tier_3_mirrors: list[str] = ['92.118.206.28', '15.204.88.113']

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
        # if True:
        for repo_path in repo_paths:
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
                logger.info("[{repo}] Will retry in {delay}", repo=repo_path, delay=retry_delay_secs)
                sleep(retry_delay_secs)
                continue
            logger.info('[{repo}] Refs: \n{refs}', repo=repo_path, refs=primary_refs[1])
            primary_health.index_snapshot = primary_refs[1].strip()
            primary_health.up = 1
            primary_health.last_in_sync = datetime.now()

            for mirror in repos_for_project[repo_path][1:]:
                mirror.git_port_open = 1 if is_port_open(str(mirror.ip_address), 9418) else 0
                mirror.in_service = 1 if str(mirror.ip_address) in current_in_service else 0
                logger.info('[{repo}] Retrieving references for mirror: {mirror} ({ip})', repo=repo_path,
                            mirror=mirror.instance, ip=mirror.ip_address)
                mirror_refs = get_ref_list(calc_repo_url(str(mirror.ip_address), repo_path))
                logger.info('[{repo}] Refs: \n{refs}', repo=repo_path, refs=mirror_refs[1])
                if mirror_refs[2]:
                    logger.error('[{repo}] Failure to retrieve references from mirror. Git error: {err}',
                                 repo=repo_path, err=mirror_refs[2])
                    mirror.sync_errors_total += 1
                    mirror.last_error_message = mirror_refs[2].strip()
                    if "unable to connect" in mirror_refs[2]:
                        mirror.up = 0
                    # TODO Discover other possible error messages
                    # Exit code 128: Valid git CLI syntax, but the remote server didn't respond.
                    # Exit code 128: Also used if .git/packed-refs is intentionally corrupted.
                else:
                    mirror.up = 1
                    mirror.index_snapshot = mirror_refs[1].strip()

                if mirror.index_snapshot == primary_health.index_snapshot:
                    mirror.in_sync = 1
                    mirror.last_in_sync = primary_health.last_in_sync
                else:
                    mirror.in_sync = 0
                    logger.error("[{repo}] OUT OF SYNC! on {mirror}", repo=repo_path, mirror=mirror.instance)

            print(render_prometheus(repos_for_project[repo_path]))
            push_to_victoria_metrics(repos_for_project[repo_path], VICTORIA_PROM_IMPORT_URL)
        sleep(retry_delay_secs)


def get_ref_list(repo_url: str) -> tuple[int, str, str]:
    # Returns a tuple of (git exit code, ls-remote output, git error messages)
    cmd = [GIT_PATH, 'ls-remote', repo_url]
    logger.info('Running {cmd}', cmd=' '.join(cmd))
    result = run(cmd, shell=True, capture_output=True)
    # print(result.stdout.decode('utf-8'))
    # print(result.stderr.decode('utf-8'))
    return result.returncode, result.stdout.decode('utf-8').strip(), result.stderr.decode('utf-8')


if __name__ == '__main__':
    with open('one_repo.txt', 'r', encoding='utf-8') as f:
        repo_paths = [l.strip() for l in f.readlines() if l.strip()]
    print(repo_paths)
    main(repo_paths)
