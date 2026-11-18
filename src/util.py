import difflib
import socket
from pathlib import Path


def is_port_open(ip: str, port: int) -> int:
    # Returns 0 on success, or an errno on failure
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if ':' in ip:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.settimeout(4)  # Connection timeout in seconds
    # noinspection PyBroadException
    try:
        result = s.connect_ex((ip, port))
        if result == 0:
            return True
        else:
            return False
    except Exception:
        return False
    finally:
        s.close()


def calc_repo_url(host: str, path: str, protocol='git', ) -> str:
    # Example git://git.git.savannah.gnu.org/test-project.git
    return f'{protocol}://{host}/{path}'


def calc_ss_diff(primary_snapshot: str, mirror_snapshot: str) -> str:
    lines1 = primary_snapshot.splitlines(keepends=True)
    lines2 = mirror_snapshot.splitlines(keepends=True)
    diff = difflib.unified_diff(lines1, lines2, fromfile='primary', tofile='mirror')
    if not diff:
        return ""
    return "".join(diff)


def calc_ss_unique(primary_snapshot: str, mirror_snapshot: str) -> tuple[set[str],set[str]]:
    lines1 = set(primary_snapshot.splitlines(keepends=False))
    lines2 = set(mirror_snapshot.splitlines(keepends=False))
    return lines1.difference(lines2), lines2.difference(lines1)


def validate_input_file_path(file_path: Path, required_extension: str = '')-> str:
    # Parameter required_extension should be blank or start with a period, such as ".yaml"
    if not file_path.is_file():
        return f'file was not found at: {file_path.absolute()}'
    if required_extension and file_path.suffix != required_extension:
        return f'file must end in {required_extension} at: {file_path.absolute()}'
    if file_path.stat().st_size == 0:
        return f'file must not be empty at: {file_path.absolute()}'
    return ''
