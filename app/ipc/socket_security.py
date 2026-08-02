"""
EiraOS IPC Socket Security Module
Enforces strict 0600 permissions on Unix Domain Sockets to prevent local privilege escalation.
"""
import os
import stat

def secure_socket_path(socket_path: str):
    if os.path.exists(socket_path):
        # Enforce strict owner-only read/write (0600) permissions
        os.chmod(socket_path, stat.S_IRUSR | stat.S_IWUSR)
        
        # Verify permissions
        file_mode = stat.S_IMODE(os.stat(socket_path).st_mode)
        if file_mode != 0o600:
            raise PermissionError(
                f"Security Warning: Socket '{socket_path}' has insecure permissions {oct(file_mode)}. "
                "Must be strictly 0600."
            )
