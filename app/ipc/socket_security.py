"""
EiraOS IPC Socket Security Module
Enforces strict 0660 / 0600 permissions on Unix Domain Sockets to prevent local privilege escalation.
"""
import os
import socket
import stat


class PeerCredentialError(PermissionError):
    """Raised when peer credentials (UID/GID) do not match expected owner."""
    pass


def secure_socket_path(socket_path: str):
    if os.path.exists(socket_path):
        os.chmod(socket_path, stat.S_IRUSR | stat.S_IWUSR)
        file_mode = stat.S_IMODE(os.stat(socket_path).st_mode)
        if file_mode != 0o600:
            raise PermissionError(
                f"Security Warning: Socket '{socket_path}' has insecure permissions {oct(file_mode)}. "
                "Must be strictly 0600."
            )


def setup_unix_socket(socket_path: str, mode: int = 0o660, group: str = "eira") -> socket.socket:
    remove_unix_socket(socket_path)
    os.makedirs(os.path.dirname(socket_path), exist_ok=True)
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o117)
    try:
        sock.bind(socket_path)
        os.chmod(socket_path, mode)
    finally:
        os.umask(old_umask)
    return sock


def remove_unix_socket(socket_path: str) -> None:
    if os.path.exists(socket_path) or os.path.islink(socket_path):
        try:
            os.remove(socket_path)
        except OSError:
            pass


def validate_peer_credentials(sock: socket.socket) -> dict:
    """Verifies SO_PEERCRED on Linux Unix sockets."""
    try:
        if hasattr(socket, "SO_PEERCRED"):
            import struct
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            pid, uid, gid = struct.unpack("3i", creds)
            return {"pid": pid, "uid": uid, "gid": gid}
    except Exception as exc:
        raise PeerCredentialError(f"Failed to validate peer credentials: {exc}") from exc
    return {"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid()}
