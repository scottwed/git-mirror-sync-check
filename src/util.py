import socket

def is_port_open(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(4)  # Connection timeout in seconds
    try:
        # Returns 0 on success, or an errno on failure
        result = s.connect_ex((ip, port))
        if result == 0:
            return True
        else:
            return False
    except Exception as e:
        return False
    finally:
        s.close()

# # Check TCP 9418 (default Git port)
# host_ip = '127.0.0.1' # Replace with your target IP
# is_up = is_port_open(host_ip, 9418)
#
# if is_up:
#     print(f"TCP {host_ip}:9418 is up and listening.")
# else:
#     print(f"TCP {host_ip}:9418 is unreachable.")
