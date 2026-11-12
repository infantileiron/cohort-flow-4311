export default function StaleNotice({stale,ruleVersion,currentVersion,text='该分析使用旧口径，结果已标记待重算。请按当前规则重新运行并复核；已批准报告保留原结果。'}:{stale:boolean;ruleVersion?:string;currentVersion?:string;text?:string}){
  if(!stale)return null;
  return <div className="notice stale"><b>待重算</b> {text}<small>旧规则：{ruleVersion||'未记录'} · 当前规则：{currentVersion||'—'}</small></div>;
}
