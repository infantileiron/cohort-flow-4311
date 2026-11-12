export const states=['active','dormant','completed','lost'] as const;
export const stateLabels=['活跃','休眠','结业','流失'];
export const roleLabels:Record<string,string>={admin:'运营复核人',analyst:'研修分析员',viewer:'课程观察员'};
export const runLabels:Record<string,string>={queued:'排队中',running:'计算中',completed:'已完成',failed:'失败',pending:'待复核',approved:'已通过',rejected:'已退回',stale:'待重算'};
export const outcomeReasonLabels:Record<string,string>={
  identified:'已识别：三项概率与有限周数均可计算',
  no_observation:'无相邻周观测：概率与周数留空，不按0处理',
  insufficient_observation:'可达状态缺少观测：后继不可识别',
  permanent_retention:'存在封闭循环：滞留概率大于0，不给有限周数',
};
