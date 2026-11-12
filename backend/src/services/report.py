import csv,io
from fastapi import HTTPException
from src.models.entities import PublishedReport
from src.config.settings import ARTIFACT_DIR
from src.utils import repository as repo
from src.utils.identity import new_id,now
from src.services.markov import RULE_VERSION

def safe_cell(value):
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@")) else value

def _report_view(report):
    item={k:v for k,v in report.items() if k!="snapshot"}
    snapshot=report.get("snapshot") or {}
    item["rule_version"]=snapshot.get("rule_version","")
    # 报告是归档物：规则更新后不重算，只如实标明它是在哪一版规则下生成的。
    item["legacy_rule"]=item["rule_version"]!=RULE_VERSION
    return item

def list_reports(): return [_report_view(item) for item in repo.all_rows("reports")]

def create(data):
    run,review=repo.get("runs",data.run_id),repo.get("reviews",data.review_id)
    if review["status"]!="approved" or review["run_id"]!=run["id"] or run["status"]!="completed": raise ValueError("报告必须引用该运行已通过的复核")
    result=run.get("result") or {}
    if result.get("rule_version")!=RULE_VERSION:
        raise ValueError("该运行使用旧口径，结果待重算；请重新运行并复核后再生成报告")
    snapshot={"result":result,"checksum":result.get("checksum",""),"rule_version":result.get("rule_version"),"captured_at":now()}
    report=repo.put("reports",PublishedReport(new_id("rpt"),data.run_id,data.review_id,data.title,now(),snapshot))
    ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
    (ARTIFACT_DIR/(report["id"]+".csv")).write_text(download(report["id"]),encoding="utf-8")
    return _report_view(report)

def download(id):
    report=repo.get("reports",id); run=repo.get("runs",report["run_id"])
    if repo.get("reviews",report["review_id"])["status"]!="approved": raise HTTPException(403,"复核未通过")
    # 已批准报告固定使用生成时的结果快照；之后规则更新或重算都不改变归档内容。
    snapshot=report.get("snapshot") or {}
    r=snapshot.get("result") or run["result"]
    display_version=snapshot.get("rule_version") or r.get("rule_version","")
    outcome_states=r.get("markov",{}).get("transition_states") or ["active","dormant"]
    out=io.StringIO();writer=csv.writer(out)
    # 报告保留生成时的结果；表头说明该快照对应的规则版本，不要求按新规则重算。
    writer.writerow(['report','rule_version','cohort_week','age','eligible','observed','active','missing','censored','retention','checksum'])
    checksum=snapshot.get("checksum") or r.get("checksum","")
    for cohort in r['cohorts']:
        for cell in cohort['cells']:
            writer.writerow([safe_cell(report['title']),display_version,cohort['cohort_week'],cell['age'],cell['eligible'],cell['observed'],cell['active'],cell['missing'],cell['censored'],cell['retention'],checksum])
    writer.writerow([]);writer.writerow(['from_state','to_state','transition_count','probability'])
    markov=r['markov']
    for i,state in enumerate(markov['states']):
        for j,target in enumerate(markov['states']):
            value=markov['matrix'][i][j]
            writer.writerow([state,target,markov['counts'][i][j],"" if value is None else value])
    writer.writerow([]);writer.writerow(['outcome_analysis','from_state','completion_probability','loss_probability','permanent_probability','expected_weeks','probabilities_identifiable','duration_identifiable','reason','outgoing_pairs'])
    for state in outcome_states:
        item=(markov.get('outcomes') or {}).get(state,{})
        writer.writerow(['per_state',state,item.get('completion_probability'),item.get('loss_probability'),item.get('permanent_probability'),item.get('expected_weeks'),item.get('probabilities_identifiable'),item.get('duration_identifiable'),item.get('reason'),item.get('outgoing_pairs')])
    return '﻿'+out.getvalue()
