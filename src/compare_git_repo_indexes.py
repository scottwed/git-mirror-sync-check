from datetime import datetime
from socket import gethostbyname, getaddrinfo
from subprocess import run
from time import sleep

from ipaddress import IPv4Address, IPv6Address

from mirror_health import GitMirrorHealth, MirrorRole

primary_repo:str = 'gw8.bru.st'
primary_repo_addr:str = gethostbyname(primary_repo)


tier_3_mirrors: list[str] = ['92.118.206.28', '5.5.5.5']
# tier_3_mirrors: list[str] = ['92.118.206.28', '15.204.88.113']
repo_paths: list[str] = [
    'test-project.git',
    # 'chess',
    # 'coreutils',
]
retry_delay = 15 # Seconds
repos_for_project: dict[str, list[GitMirrorHealth]] = dict()

# TODO implement a snapshot history (last 5-10 index snapshot hashes) to estimate how stale the mirror is.
# TODO consider adding a last contact timestamp to the mirror health class

def main():
    if primary_repo and tier_3_mirrors:
        current_in_service = [a[4][0] for a in getaddrinfo('git.git.savannah.gnu.org', 22)]
        print(current_in_service)
        # while True:
        if True:
            for repo_path in repo_paths:
                # TODO Fix invalid assumption that user provided IP addresses are IPv4 (*2)
                if repo_path not in repos_for_project:
                    primary_health = GitMirrorHealth(
                        project=repo_path, mirror_host=primary_repo, ip_address=IPv4Address(primary_repo_addr),
                        role=MirrorRole.primary, up=0, in_service=1, in_sync=1,
                        last_in_sync=datetime.now(), sync_errors_total=0, last_error_message="",
                        index_snapshot=""
                    )
                    repos_for_project[repo_path] = [primary_health]
                    # Create placeholders for all the mirrors
                    for mirror in tier_3_mirrors:
                        mh = GitMirrorHealth(
                        project=repo_path, mirror_host=mirror, ip_address=IPv4Address(mirror),
                        role=MirrorRole.tertiary, up=0, in_service=1, in_sync=0,
                        last_in_sync=datetime.min, sync_errors_total=0, last_error_message="",
                        index_snapshot="")
                        repos_for_project[repo_path].append(mh)

                else:
                    primary_health = repos_for_project[repo_path][0]

                print(f"[{repo_path}] Retrieving latest index entries for primary: ({primary_repo})")
                index_primary = get_index_head(calc_repo_url(primary_repo, repo_path))
                print()
                print(index_primary[0])
                if index_primary[2]:
                    print(f'[{repo_path}] Failure to retrieve index from primary. Git error: {index_primary[2]}')
                    primary_health.last_error_message = index_primary[2]
                    primary_health.sync_errors_total += 1
                    print(f'Will retry in {retry_delay}')
                    sleep(retry_delay)
                    continue
                print(index_primary[1])
                primary_health.index_snapshot = index_primary[1].strip()
                primary_health.up = 1
                primary_health.last_in_sync=datetime.now()

                for mirror in repos_for_project[repo_path][1:]:
                    mirror.in_service = 1 if str(mirror.ip_address) in current_in_service else 0
                    print(f'[{repo_path}] Retrieving latest index entries for mirror: ({mirror.mirror_host})')
                    index_mirror = get_index_head(calc_repo_url(str(mirror.ip_address), repo_path))
                    print(index_mirror[0])
                    if index_mirror[2]:
                        print(f'[{repo_path}] Failure to retrieve index from mirror. Git error: {index_mirror[2]}')
                        mirror.sync_errors_total += 1
                        mirror.last_error_message = index_mirror[2].strip()
                        if "unable to connect" in index_mirror[2]:
                            mirror.up = False
                        # TODO Discover other possible error messages
                    else:
                        mirror.up = True
                        mirror.index_snapshot = index_mirror[1].strip()

                    if mirror.index_snapshot == primary_health.index_snapshot:
                        mirror.in_sync = 1
                        mirror.last_in_sync = primary_health.last_in_sync

                    # print(index_mirror[1])
            from pprint import pprint
            for r, m in repos_for_project.items():
                for mh in m:
                    print()
                    pprint(mh)
                    print(mh.to_prometheus_samples())


def get_index_head(repo_url: str) -> tuple[int, str, str]:
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