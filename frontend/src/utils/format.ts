export const percent=(v:number|null|undefined)=>v==null?'未观测':(v*100).toFixed(1)+'%';
export const decimal=(v:number|null|undefined)=>v==null?'不可识别':v.toFixed(2);
// 概率：null 明确区分“没有观测”与“不可识别”，不显示为 0。
export const probability=(v:number|null|undefined,reason?:string)=>{
  if(v==null)return reason==='no_observation'?'未观测':(reason==='insufficient_observation'?'不可识别':'无法计算');
  return (v*100).toFixed(1)+'%';
};
// 周数：永久滞留意味着期望为无穷，不能给有限值。
export const weeks=(v:number|null|undefined,reason?:string)=>{
  if(v==null){
    if(reason==='permanent_retention')return '无有限值（永久滞留）';
    if(reason==='no_observation')return '未观测';
    if(reason==='insufficient_observation')return '不可识别（后继缺观测）';
    return '不可识别';
  }
  return v.toFixed(2)+' 周';
};
