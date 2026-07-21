import socket

def is_port_open(ip, port):
    # Returns 0 on success, or an errno on failure
    s = None
    if ':' in ip:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(4)  # Connection timeout in seconds
    try:
        result = s.connect_ex((ip, port))
        if result == 0:
            return True
        else:
            return False
    except Exception as e:
        return False
    finally:
        s.close()

def calc_repo_url(host: str, path: str, protocol='git', ) -> str:
    # Example git://git.git.savannah.gnu.org/test-project.git
    return f'{protocol}://{host}/{path}'
