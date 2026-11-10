from __future__ import annotations

import argparse
import json
from datetime import timedelta

from app.auth.delegation import DelegationCreateRequest, DelegationScope
from app.ipc.client import IpcClient


def _delta(value: str) -> timedelta:
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    unit = value[-1] if value[-1:] in units else "h"
    number = value[:-1] if unit != "h" else value
    return timedelta(**{units[unit]: int(number)})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EiraOS Delegation Management")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--delegee", required=True)
    create.add_argument("--scope", required=True)
    create.add_argument("--expires-in", default="24h")
    create.add_argument("--session-id", required=True)

    revoke = sub.add_parser("revoke")
    revoke.add_argument("delegation_id")
    revoke.add_argument("--session-id", required=True)

    listing = sub.add_parser("list")
    listing.add_argument("--session-id", required=True)

    check = sub.add_parser("check")
    check.add_argument("--delegee", required=True)
    check.add_argument("--action", required=True)
    check.add_argument("--target", required=True)

    args = parser.parse_args(argv)
    client = IpcClient("delegationd")

    if args.command == "create":
        request = DelegationCreateRequest(
            delegee_id=args.delegee,
            scope=DelegationScope.model_validate(json.loads(args.scope)),
            expires_in=_delta(args.expires_in),
        )
        result = client.call(
            "delegation.create",
            {**request.model_dump(mode="json"), "session_id": args.session_id},
        )
    elif args.command == "revoke":
        result = client.call(
            "delegation.revoke",
            {"delegation_id": args.delegation_id, "session_id": args.session_id},
        )
    elif args.command == "list":
        result = client.call("delegation.list", {"session_id": args.session_id})
    else:
        result = client.call(
            "delegation.check",
            {
                "delegee_id": args.delegee,
                "action": args.action,
                "target": args.target,
            },
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
