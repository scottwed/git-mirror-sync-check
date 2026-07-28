import socket
import difflib

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
    return "".join(diff)
