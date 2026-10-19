# EiraOS socket permissions

## Security policy

EiraOS Unix-domain sockets use strict filesystem permissions and an explicit group
ownership policy. The configured `eira` group is preferred for group ownership. If the group is
missing, EiraOS logs a warning and disables group-ownership enforcement for that
socket instead of failing startup. The socket mode policy remains active.

### Root policy

**Root (UID 0) is intentionally allowed.** This is an explicit security decision:
the local root account is treated as a trusted administrative principal for IPC
access checks. Group and UID allow-lists still apply to non-root peers.

### Group policy

For peer-credential checks, EiraOS evaluates the peer's primary GID and its Linux
supplementary groups. A match against an allowed group is sufficient for access.

### Failure policy

Socket setup fails loudly when `chown` fails. A missing group is an environment-tolerant
condition: it is logged and group ownership enforcement is disabled. The partially
created socket is still removed if another socket setup operation fails.

`secure_socket_path` verifies the existing mode before applying the expected
0600 mode. It never validates a permission value that it has just written itself.
