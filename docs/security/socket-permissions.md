# EiraOS socket permissions

## Security policy

EiraOS Unix-domain sockets use strict filesystem permissions and an explicit group
ownership policy. The configured `eira` group is required; a missing group is a
startup/configuration error and is never silently replaced with the process GID.

### Root policy

**Root (UID 0) is intentionally allowed.** This is an explicit security decision:
the local root account is treated as a trusted administrative principal for IPC
access checks. Group and UID allow-lists still apply to non-root peers.

### Group policy

For peer-credential checks, EiraOS evaluates the peer's primary GID and its Linux
supplementary groups. A match against an allowed group is sufficient for access.

### Failure policy

Socket setup fails loudly when group resolution or `chown` fails. The partially
created socket is removed before the error is propagated so a failed setup cannot
leave an unexpectedly accessible endpoint behind.

`secure_socket_path` verifies the existing mode before applying the expected
0600 mode. It never validates a permission value that it has just written itself.
