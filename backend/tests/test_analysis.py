"""可手算样本核对：留存分母与按起始状态的终态概率。

运行：cd backend && python3 -I -m unittest discover -s tests
（算法只依赖标准库，无需 numpy。）
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.markov import absorbing_summary, transition_analysis
from src.services.retention import weekly_snapshots, retention_matrix


HAND_ROWS = [
    # A：活跃 -> 休眠 -> 结业（结业后保持结业）
    {"event_id": "a1", "learner_id": "A", "week": 1, "state": "active", "sequence": 10},
    {"event_id": "a2", "learner_id": "A", "week": 2, "state": "dormant", "sequence": 10},
    {"event_id": "a3", "learner_id": "A", "week": 3, "state": "completed", "sequence": 10},
    {"event_id": "a4", "learner_id": "A", "week": 4, "state": "completed", "sequence": 10},
    # B：活跃 -> 活跃 -> 流失
    {"event_id": "b1", "learner_id": "B", "week": 1, "state": "active", "sequence": 10},
    {"event_id": "b2", "learner_id": "B", "week": 2, "state": "active", "sequence": 10},
    {"event_id": "b3", "learner_id": "B", "week": 3, "state": "lost", "sequence": 10},
    # C：休眠自循环（无终态）；用于证明“无观测”和“封闭循环”不是同一件事
    {"event_id": "c1", "learner_id": "C", "week": 1, "state": "dormant", "sequence": 10},
    {"event_id": "c2", "learner_id": "C", "week": 2, "state": "dormant", "sequence": 10},
    {"event_id": "c3", "learner_id": "C", "week": 3, "state": "dormant", "sequence": 10},
    {"event_id": "c4", "learner_id": "C", "week": 4, "state": "dormant", "sequence": 10},
    # D：第2周缺测；相邻周迁移不得跨缺测推断
    {"event_id": "d1", "learner_id": "D", "week": 1, "state": "active", "sequence": 10},
    {"event_id": "d3", "learner_id": "D", "week": 3, "state": "completed", "sequence": 10},
]


def hand_counts():
    snapshots = weekly_snapshots(HAND_ROWS, 4)
    counts = [[0] * 4 for _ in range(4)]
    states = ["active", "dormant", "completed", "lost"]
    for weeks in snapshots.values():
        for week, entry in weeks.items():
            if week + 1 in weeks:
                counts[states.index(entry["state"])][states.index(weeks[week + 1]["state"])] += 1
    return snapshots, counts


class HandCalculableMarkovTest(unittest.TestCase):
    def test_counts_skip_missing_week(self):
        _, counts = hand_counts()
        # A: active->dormant, dormant->completed, completed->completed
        # B: active->active, active->lost
        # C: dormant->dormant 3 次
        # D: 第1周与第3周不相邻，不产生迁移对
        self.assertEqual(counts, [[1, 1, 0, 1], [0, 3, 1, 0], [0, 0, 1, 0], [0, 0, 0, 0]])

    def test_per_state_probabilities_are_hand_checkable(self):
        _, counts = hand_counts()
        result = absorbing_summary(counts)
        active = result["outcomes"]["active"]
        dormant = result["outcomes"]["dormant"]
        # P = active 行 (1/3, 1/3, 0, 1/3); dormant 行 (0, 3/4, 1/4, 0)
        # N = (I-Q)^-1 = [[3/2, 2], [0, 4]]
        # 活跃：结业 3/2*0 + 2*1/4 = 0.5；流失 3/2*1/3 = 0.5；预计 3.5 周
        self.assertAlmostEqual(active["completion_probability"], 0.5)
        self.assertAlmostEqual(active["loss_probability"], 0.5)
        self.assertAlmostEqual(active["permanent_probability"], 0.0)
        self.assertAlmostEqual(active["expected_weeks"], 3.5)
        # 休眠：结业 1，流失 0，预计 4 周
        self.assertAlmostEqual(dormant["completion_probability"], 1.0)
        self.assertAlmostEqual(dormant["loss_probability"], 0.0)
        self.assertAlmostEqual(dormant["expected_weeks"], 4.0)
        self.assertEqual(active["outgoing_pairs"], 3)
        self.assertEqual(dormant["outgoing_pairs"], 4)
        self.assertEqual(active["reason"], "identified")
        self.assertTrue(result["identifiable"])
        self.assertTrue(result["all_durations_finite"])

    def test_outcomes_kept_even_if_one_state_has_no_observation(self):
        # 活跃无任何相邻周观测，休眠正常；不能用全局 null 把休眠也抹掉
        result = absorbing_summary([[0, 0, 0, 0], [0, 3, 1, 0], [0, 0, 1, 0], [0, 0, 0, 0]])
        active = result["outcomes"]["active"]
        dormant = result["outcomes"]["dormant"]
        self.assertEqual(active["reason"], "no_observation")
        self.assertIsNone(active["completion_probability"])
        self.assertIsNone(active["expected_weeks"])
        self.assertEqual(dormant["reason"], "identified")
        self.assertAlmostEqual(dormant["expected_weeks"], 4.0)
        self.assertEqual(result["matrix"][0], [None, None, None, None])

    def test_closed_transient_loop_has_no_finite_duration(self):
        # 活跃与休眠互相转移，永不吸收：长期滞留=1，有限周数不存在
        result = absorbing_summary([[0, 2, 0, 0], [2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        for state in ("active", "dormant"):
            item = result["outcomes"][state]
            self.assertEqual(item["reason"], "permanent_retention")
            self.assertAlmostEqual(item["completion_probability"], 0.0)
            self.assertAlmostEqual(item["loss_probability"], 0.0)
            self.assertAlmostEqual(item["permanent_probability"], 1.0)
            self.assertIsNone(item["expected_weeks"])
            self.assertFalse(item["duration_identifiable"])
        self.assertTrue(result["identifiable"])  # 概率可识别（都是0）
        self.assertFalse(result["all_durations_finite"])
        self.assertIn("封闭循环", result["warning"])

    def test_reachable_unobserved_state_is_not_assumed_zero(self):
        # 活跃会进入休眠，但休眠没有任何相邻周观测；不得把休眠后继当作0或自环
        result = absorbing_summary([[1, 1, 0, 0], [0, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        active = result["outcomes"]["active"]
        self.assertEqual(active["reason"], "insufficient_observation")
        self.assertEqual(active["unobserved_downstream"], ["dormant"])
        self.assertIsNone(active["completion_probability"])
        self.assertIsNone(active["expected_weeks"])


class HandCalculableRetentionTest(unittest.TestCase):
    def test_retention_denominator_and_missing(self):
        snapshots, _ = hand_counts()
        cells = retention_matrix(snapshots, 4, False)[0]["cells"]
        # 全部 4 人都在第1周入组；年龄 1 时 D 缺测 => 留存率不发布；年龄 4 超出截止 => 右删失
        self.assertEqual(cells[0]["eligible"], 4)
        self.assertEqual(cells[0]["observed"], 4)
        self.assertEqual(cells[0]["active"], 3)
        self.assertAlmostEqual(cells[0]["retention"], 0.75)
        self.assertEqual(cells[1]["missing"], 1)
        self.assertIsNone(cells[1]["retention"])
        self.assertEqual(cells[2]["active"], 0)
        self.assertAlmostEqual(cells[2]["retention"], 0.0)
        self.assertEqual(cells[4]["censored"], 4)
        self.assertEqual(cells[4]["eligible"], 0)
        self.assertIsNone(cells[4]["retention"])


class DemoNumbersTest(unittest.TestCase):
    """与 seed 的 900 条模拟事件对齐；数值已在批次外用手算交叉核对。"""

    def test_demo_transition_outcomes(self):
        # 由 seed 生成规则直接得到的相邻周计数
        result = absorbing_summary([
            [169, 65, 35, 18],
            [36, 19, 6, 6],
            [0, 0, 91, 0],
            [0, 0, 0, 35],
        ])
        self.assertAlmostEqual(result["outcomes"]["active"]["expected_weeks"], 5.454572803850782, places=9)
        self.assertAlmostEqual(result["outcomes"]["active"]["completion_probability"], 0.6227436823104694, places=9)
        self.assertAlmostEqual(result["outcomes"]["active"]["loss_probability"], 0.3772563176895307, places=9)
        self.assertAlmostEqual(result["outcomes"]["dormant"]["expected_weeks"], 5.486762936221419, places=9)
        self.assertAlmostEqual(result["outcomes"]["dormant"]["completion_probability"], 0.5920577617328519, places=9)
        self.assertAlmostEqual(result["outcomes"]["dormant"]["loss_probability"], 0.4079422382671479, places=9)


class TransitionOrchestrationTest(unittest.TestCase):
    def test_transition_analysis_uses_adjacent_pairs_only(self):
        snapshots, _ = hand_counts()
        result = transition_analysis(snapshots)
        self.assertEqual(result["adjacent_pairs"], 8)  # A3+B2+C3；D 跨缺测周不计


if __name__ == "__main__":
    unittest.main()
