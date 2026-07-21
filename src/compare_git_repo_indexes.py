from datetime import datetime
from socket import gethostbyname, getaddrinfo
from subprocess import run
from sys import exit
from time import sleep

from ipaddress import IPv4Address, IPv6Address

from mirror_health import GitMirrorHealth, MirrorRole, push_to_victoria_metrics, render_prometheus
from util import is_port_open

primary_repo:str = 'gw8.bru.st'
primary_repo_addr:str = gethostbyname(primary_repo)
repo_rr_record = 'git.git.savannah.gnu.org'

# tier_3_mirrors: list[str] = ['92.118.206.28', '5.5.5.5', '15.204.88.113']
tier_3_mirrors: list[str] =['176.100.37.193', '185.112.147.164', '135.148.138.35', '15.204.9.231',
                            '15.204.88.113', '51.255.194.124', '92.118.206.28', '176.100.37.192',
                            '178.104.15.118']
# tier_3_mirrors: list[str] = ['92.118.206.28', '15.204.88.113']
repo_paths: list[str] = [
    'test-project.git',
    # 'chess',
    # 'coreutils',
]
# retry_delay = 30 # Seconds
# retry_delay = 30 # Seconds


# Git remote ports - 22 SSH, 80 HTTP, 443 HTTPS, 9418 GIT R/O anon

# TODO implement a snapshot history (last 5-10 snapshot hashes) to estimate the staleness of the mirror.
# TODO write alert logic.  Alert on up=0 for > x minutes, git_port_open=0 > x minutes, in_service=0 > 26 hours
# TODO Isolate port_open check from project-level checking.

def main():
    if not (primary_repo and tier_3_mirrors and repo_paths):
        print("Missing one or more required inputs!")
        exit(1)

    repos_for_project: dict[str, list[GitMirrorHealth]] = dict()
    current_in_service = [a[4][0] for a in getaddrinfo('%s' % repo_rr_record, 22)]
    print(current_in_service)
    while True:
        sleep(retry_delay)
    # if True:
        for repo_path in repo_paths:
            # TODO Fix invalid assumption that user provided IP addresses are IPv4 (*2)
            if repo_path not in repos_for_project:
                primary_health = GitMirrorHealth(
                    project=repo_path, instance=primary_repo, ip_address=IPv4Address(primary_repo_addr),
                    role=MirrorRole.primary, up=0, in_service=1, in_sync=1,
                    last_in_sync=datetime.now(), sync_errors_total=0, last_error_message="",
                    index_snapshot=""
                )
                repos_for_project[repo_path] = [primary_health]
                # Create placeholders for all the mirrors
                for mirror in tier_3_mirrors:
                    mh = GitMirrorHealth(
                    project=repo_path, instance=mirror, ip_address=IPv4Address(mirror),
                    role=MirrorRole.tertiary, up=0, in_service=1, in_sync=0,
                    last_in_sync=datetime.min, sync_errors_total=0, last_error_message="",
                    index_snapshot="")
                    repos_for_project[repo_path].append(mh)

            else:
                primary_health = repos_for_project[repo_path][0]

            print(f"[{repo_path}] Retrieving references from primary: ({primary_repo})")
            primary_health.git_port_open = 1 if is_port_open(str(primary_health.ip_address), 9418) else 0
            primary_refs = get_ref_list(calc_repo_url(primary_repo, repo_path))
            print()
            # print(primary_refs[0])
            if primary_refs[2]:
                print(f'[{repo_path}] Failure to retrieve references from primary. Git error: {primary_refs[2]}')
                primary_health.last_error_message = primary_refs[2]
                primary_health.sync_errors_total += 1
                print(f'[{repo_path}] Will retry in {retry_delay}')
                sleep(retry_delay)
                continue
            print(primary_refs[1])
            primary_health.index_snapshot = primary_refs[1].strip()
            primary_health.up = 1
            primary_health.last_in_sync=datetime.now()

            for mirror in repos_for_project[repo_path][1:]:
                mirror.git_port_open = 1 if is_port_open(str(mirror.ip_address), 9418) else 0
                mirror.in_service = 1 if str(mirror.ip_address) in current_in_service else 0
                print(f'[{repo_path}] Retrieving references for mirror: {mirror.instance} ({mirror.ip_address})')
                mirror_refs = get_ref_list(calc_repo_url(str(mirror.ip_address), repo_path))
                print(mirror_refs[0])
                if mirror_refs[2]:
                    print(f'[{repo_path}] Failure to retrieve references from mirror. Git error: {mirror_refs[2]}')
                    mirror.sync_errors_total += 1
                    mirror.last_error_message = mirror_refs[2].strip()
                    if "unable to connect" in mirror_refs[2]:
                        mirror.up = 0
                    # TODO Discover other possible error messages
                    # Exit code 128 is for valid syntax but the remote server didn't respond.
                    # The exit code is also 128 if .git/packed-refs is intentionally corrupted.
                else:
                    mirror.up = 1
                    mirror.index_snapshot = mirror_refs[1].strip()

                if mirror.index_snapshot == primary_health.index_snapshot:
                    mirror.in_sync = 1
                    mirror.last_in_sync = primary_health.last_in_sync

                # print(index_mirror[1])
        from pprint import pprint
        for r, m in repos_for_project.items():
            print()
            # for mh in m:
            #     print()
            #     pprint(mh)
            #     print()
                # print(render_prometheus([mh]))
            pprint(render_prometheus(m))
            push_to_victoria_metrics(m, r'http://127.0.0.1:8428/api/v1/import/prometheus')


def get_ref_list(repo_url: str) -> tuple[int, str, str]:
    # cmd = [r'C:\Program Files\Git\cmd\git.exe', 'ls-remote', '--sort=-committerdate', repo_url, '|', 'tail', '-1000']
    # FIXME path to git shouldn't be hard coded here
    cmd = [r'C:\Program Files\Git\cmd\git.exe', 'ls-remote', repo_url]
    print(f'Running {' '.join(cmd)}')
    result = run(cmd, shell=True, capture_output=True)
    # print(result.stdout.decode('utf-8'))
    # print(result.stderr.decode('utf-8'))
    return result.returncode, result.stdout.decode('utf-8').strip(), result.stderr.decode('utf-8')


def calc_repo_url(host: str, path: str, protocol='git', ) -> str:
    # git://git.git.savannah.gnu.org/test-project.git
     return f'{protocol}://{host}/{path}'

if __name__ == '__main__':
    main()