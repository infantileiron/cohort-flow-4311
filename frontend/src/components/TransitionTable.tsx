import type {Run} from '../types/entities';
import {stateLabels,outcomeReasonLabels} from '../constants/enums';
import {percent,probability,weeks} from '../utils/format';
export default function TransitionTable({run}:{run:Run}){
  const m=run.result.markov;
  const states=m.transition_states||['active','dormant'];
  const label=(s:string)=>stateLabels[m.states.indexOf(s)]||s;
  const outcomes=m.outcomes;
  return <>
    <div className="table-scroll"><table><thead><tr><th>本周 → 下周</th>{stateLabels.map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{m.matrix.map((row,i)=><tr key={i}><th>{stateLabels[i]}</th>{row.map((v,j)=><td key={j} title={v==null?'该状态无相邻周观测，不以自环代替':''}>{percent(v)}<small>{m.counts[i][j]} 次观测迁移</small></td>)}</tr>)}</tbody></table></div>
    {outcomes?<><h3 className="subhead">按起始状态：结业、流失、长期滞留</h3>
      <p className="annotation">每一行表示“当前处于该状态、尚未结业或流失”的学员最终去向。预计周数含当前周；无观测记为空值，有永久滞留可能时不给出有限周数。</p>
      <div className="table-scroll"><table><thead><tr><th>起始状态</th><th>结业概率</th><th>流失概率</th><th>长期滞留概率</th><th>预计周数</th><th>观测迁移对</th><th>可识别性说明</th></tr></thead><tbody>{states.map(s=>{const o=outcomes?.[s];return o?<tr key={s}><th>{label(s)}</th><td>{probability(o.completion_probability,o.reason)}</td><td>{probability(o.loss_probability,o.reason)}</td><td>{probability(o.permanent_probability,o.reason)}</td><td>{weeks(o.expected_weeks,o.reason)}</td><td>{o.outgoing_pairs}</td><td><small>{outcomeReasonLabels[o.reason]||o.reason}{o.unobserved_downstream?.length?`：${o.unobserved_downstream.map(x=>label(x)).join('、')}无观测`:''}</small></td></tr>:null})}</tbody></table></div></>
      :<p className="annotation">该结果由旧口径生成，没有按起始状态的终态概率；请按当前规则重新运行后再阅读。</p>}
    {m.warning&&<p className="annotation">{m.warning}</p>}
  </>;
}
