from __future__ import annotations
import argparse,json
from datetime import timedelta
from app.auth.delegation import DelegationCreateRequest,DelegationScope
from app.ipc.client import IpcClient
def _delta(value):
    units={"s":"seconds","m":"minutes","h":"hours","d":"days"}
    unit=value[-1] if value[-1:] in units else "h"
    number=value[:-1] if unit!="h" else value
    return timedelta(**{units[unit]:int(number)})
def main(argv=None):
    parser=argparse.ArgumentParser(description="EiraOS Delegation Management")
    sub=parser.add_subparsers(dest="command",required=True)
    c=sub.add_parser("create");c.add_argument("--delegee",required=True);c.add_argument("--scope",required=True);c.add_argument("--expires-in",default="24h");c.add_argument("--session-id",required=True)
    r=sub.add_parser("revoke");r.add_argument("delegation_id");r.add_argument("--session-id",required=True)
    l=sub.add_parser("list");l.add_argument("--session-id",required=True)
    q=sub.add_parser("check");q.add_argument("--delegee",required=True);q.add_argument("--action",required=True);q.add_argument("--target",required=True)
    a=parser.parse_args(argv);client=IpcClient("delegationd")
    if a.command=="create":
        req=DelegationCreateRequest(delegee_id=a.delegee,scope=DelegationScope.model_validate(json.loads(a.scope)),expires_in=_delta(a.expires_in))
        result=client.call("delegation.create",{**req.model_dump(mode="json"),"session_id":a.session_id})
    elif a.command=="revoke":
        result=client.call("delegation.revoke",{"delegation_id":a.delegation_id,"session_id":a.session_id})
    elif a.command=="list":
        result=client.call("delegation.list",{"session_id":a.session_id})
    else:
        result=client.call("delegation.check",{"delegee_id":a.delegee,"action":a.action,"target":a.target})
    print(json.dumps(result,indent=2,ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
