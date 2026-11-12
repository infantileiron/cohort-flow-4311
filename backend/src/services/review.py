from fastapi import HTTPException
from src.constants.enums import ReviewStatus
from src.models.entities import SegmentReview
from src.utils import repository as repo
from src.utils.identity import new_id, now
from src.services.markov import RULE_VERSION

def _review_view(item):
    run=repo.get("runs",item["run_id"])
    result=run.get("result") or {}
    stale=bool(result) and result.get("rule_version")!=RULE_VERSION
    item=dict(item);item["stale"]=stale;item["rule_version"]=result.get("rule_version","")
    return item

def list_reviews(): return [_review_view(item) for item in repo.all_rows("reviews")]

def create(data,user):
    run=repo.get("runs",data.run_id)
    if run["status"]!="completed": raise ValueError("只有已完成的运行可提交复核")
    if (run.get("result") or {}).get("rule_version")!=RULE_VERSION: raise ValueError("该运行使用旧口径，结果待重算；请重新运行后再提交复核")
    if any(r["run_id"]==data.run_id and r["status"] in ("pending","approved") for r in repo.all_rows("reviews")): raise HTTPException(409,"该运行已有待审或通过的复核")
    item=SegmentReview(new_id("rev"),data.run_id,data.comment,created_at=now())
    return _review_view(repo.put("reviews",item))

def decide(id,data,user):
    item=repo.get("reviews",id)
    if item["status"]!=ReviewStatus.PENDING.value: raise HTTPException(409,"该复核已处理")
    run=repo.get("runs",item["run_id"])
    if data.status=="approved" and (run.get("result") or {}).get("rule_version")!=RULE_VERSION: raise ValueError("该运行使用旧口径，结果待重算；不能批准旧结果")
    item.update(status=data.status,comment=data.comment,reviewer=user["email"])
    return _review_view(repo.put("reviews",item))
