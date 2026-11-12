"""按起始状态给出结业、流失、长期滞留概率与预计周数。

口径要点：
- 只使用有相邻日历周观测的状态对；缺失周不推断、不前填。
- 每个暂态起始状态单独判断可识别性，不用一个全局空值抹掉全部状态。
- 无相邻观测的状态：概率与周数为 null（无观测），不是 0。
- 可达但本身无观测的暂态：后继分布未知，概率与周数均为 null（不可识别）。
- 能进入不吸收的暂态封闭循环：滞留概率 > 0，吸收概率仍可识别，但不输出有限预计周数。
- 预计周数含当前周；任何情况下都不添加平滑伪计数。
"""
from math import isfinite
from src.constants.states import STATES, TRANSIENT

# 规则版本：分析口径发生任何语义变化时必须递增。
# 旧运行不带该版本（或版本不同）即视为“待重算”，结果页/报告/复核均据此提示。
RULE_VERSION = "2026-11-per-state-outcome-v2"


def _outcome(reason: str, **values) -> dict:
    item = {
        "completion_probability": None,
        "loss_probability": None,
        "permanent_probability": None,
        "expected_weeks": None,
        "probabilities_identifiable": False,
        "duration_identifiable": False,
        "reason": reason,
        "outgoing_pairs": 0,
    }
    item.update(values)
    return item


def _validate(counts) -> list[list[float]]:
    try:
        rows = [[float(value) for value in row] for row in counts]
    except (TypeError, ValueError):
        raise ValueError("迁移计数矩阵无效") from None
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        raise ValueError("迁移计数矩阵无效")
    if any(value < 0 or not isfinite(value) for row in rows for value in row):
        raise ValueError("迁移计数矩阵无效")
    return rows


def _reachable(start: int, q: list[list[float]]) -> set[int]:
    seen, stack = {start}, [start]
    while stack:
        node = stack.pop()
        for nxt in range(len(q)):
            if q[node][nxt] > 0 and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _can_absorb(start: int, q: list[list[float]], r: list[list[float]]) -> bool:
    """在暂态子图内从 start 出发，是否存在一步直接进入吸收态的可能。"""
    return any(sum(r[node]) > 0 for node in _reachable(start, q))


def _invert(matrix: list[list[float]]) -> list[list[float]]:
    """2x2 以内的小矩阵求逆，足够覆盖 active/dormant 子链。"""
    size = len(matrix)
    if size == 0:
        return []
    if size == 1:
        if abs(matrix[0][0]) < 1e-12:
            raise ValueError("迁移子链不可逆")
        return [[1.0 / matrix[0][0]]]
    det = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    if abs(det) < 1e-12:
        raise ValueError("迁移子链不可逆")
    return [
        [matrix[1][1] / det, -matrix[0][1] / det],
        [-matrix[1][0] / det, matrix[0][0] / det],
    ]


def _matmul(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(a * b for a, b in zip(row, vector)) for row in matrix]


def _sub_chain(
    states: list[int],
    q: list[list[float]],
    targets: list[list[float]],
) -> tuple[list[list[float]], list[list[float]]]:
    """在 states 上求基本矩阵 N=(I-Q)^-1 与吸收概率 N*R。"""
    size = len(states)
    i_minus_q = [
        [(1.0 if row == col else 0.0) - q[states[row]][states[col]] for col in range(size)]
        for row in range(size)
    ]
    n = _invert(i_minus_q)
    absorption = [
        _matmul(n, [targets[state][k] for state in states]) for k in range(len(targets[0]))
    ]
    # 转成按状态的行
    return n, [
        [absorption[k][row] for k in range(len(targets[0]))] for row in range(size)
    ]


def absorbing_summary(counts) -> dict:
    counts = _validate(counts)
    observed = [sum(row) for row in counts]
    q = [[0.0, 0.0], [0.0, 0.0]]
    r = [[0.0, 0.0], [0.0, 0.0]]
    for row in range(2):
        total = observed[row]
        if total:
            q[row] = [counts[row][0] / total, counts[row][1] / total]
            r[row] = [counts[row][2] / total, counts[row][3] / total]

    outcomes: dict[str, dict] = {}
    for row, state in enumerate(TRANSIENT):
        pairs = int(observed[row])
        if not pairs:
            outcomes[state] = _outcome("no_observation")
            continue
        reach = _reachable(row, q)
        unobserved = sorted(
            TRANSIENT[node] for node in reach if node != row and not observed[node]
        )
        if unobserved:
            outcomes[state] = _outcome(
                "insufficient_observation",
                outgoing_pairs=pairs,
                unobserved_downstream=unobserved,
            )
            continue

        closed = {node for node in reach if not _can_absorb(node, q, r)}
        if row in closed:
            outcomes[state] = _outcome(
                "permanent_retention",
                completion_probability=0.0,
                loss_probability=0.0,
                permanent_probability=1.0,
                probabilities_identifiable=True,
                outgoing_pairs=pairs,
            )
            continue

        open_states = sorted(node for node in reach if node not in closed)
        targets = [[0.0, 0.0, 0.0] for _ in range(2)]
        for node in open_states:
            targets[node][0] = r[node][0]
            targets[node][1] = r[node][1]
            targets[node][2] = sum(q[node][closed_node] for closed_node in closed)
        n, absorption = _sub_chain(open_states, q, targets)
        index = open_states.index(row)
        completion = absorption[index][0]
        loss = absorption[index][1]
        permanent = absorption[index][2]
        total = completion + loss + permanent
        probabilities_identifiable = abs(total - 1.0) < 1e-9
        if permanent > 1e-12:
            outcomes[state] = _outcome(
                "permanent_retention",
                completion_probability=completion,
                loss_probability=loss,
                permanent_probability=permanent,
                probabilities_identifiable=probabilities_identifiable,
                outgoing_pairs=pairs,
            )
            continue
        outcomes[state] = _outcome(
            "identified",
            completion_probability=completion,
            loss_probability=loss,
            permanent_probability=0.0,
            expected_weeks=sum(n[index]),
            probabilities_identifiable=probabilities_identifiable,
            duration_identifiable=probabilities_identifiable,
            outgoing_pairs=pairs,
        )

    warnings = []
    if any(item["reason"] == "permanent_retention" for item in outcomes.values()):
        warnings.append("存在暂态封闭循环：相关起始状态滞留概率大于0，不输出有限预计周数；未添加平滑伪计数")
    if any(item["reason"] == "insufficient_observation" for item in outcomes.values()):
        warnings.append("某一暂态状态可达但本身无相邻周观测：后继分布不可识别，不按0或自环处理")
    if any(item["reason"] == "no_observation" for item in outcomes.values()):
        warnings.append("至少一个暂态状态没有任何相邻周观测：概率与周数记为未观测，不按0处理")

    # 迁移概率表：任何没有相邻周观测的行都留空（None），不用自环伪造观测；
    # 终态在模型中按吸收态处理，但“无观测”不能在展示上被写成 100%。
    matrix: list[list[float | None]] = []
    for row in range(4):
        if observed[row]:
            matrix.append([value / observed[row] for value in counts[row]])
        else:
            matrix.append([None, None, None, None])

    probabilities_identifiable = all(
        item["probabilities_identifiable"] for item in outcomes.values()
    )
    return {
        "states": list(STATES),
        "transition_states": list(TRANSIENT),
        "counts": [[int(value) for value in row] for row in counts],
        "observed_pairs": [int(value) for value in observed],
        "matrix": matrix,
        "outcomes": outcomes,
        # 兼容旧字段：仍按起始状态逐项给出，不用单个 null 抹掉全部状态。
        "expected_weeks": [outcomes[state]["expected_weeks"] for state in TRANSIENT],
        "absorption": [
            [outcomes[state]["completion_probability"], outcomes[state]["loss_probability"]]
            for state in TRANSIENT
        ],
        "identifiable": probabilities_identifiable,
        "all_durations_finite": all(
            item["duration_identifiable"] for item in outcomes.values()
        ),
        "rule_version": RULE_VERSION,
        "warning": "；".join(warnings),
    }


def transition_analysis(snapshots) -> dict:
    counts = [[0, 0, 0, 0] for _ in range(4)]
    pairs = 0
    for weeks in snapshots.values():
        for week, entry in weeks.items():
            if week + 1 in weeks:
                counts[STATES.index(entry["state"])][STATES.index(weeks[week + 1]["state"])] += 1
                pairs += 1
    return {"adjacent_pairs": pairs, **absorbing_summary(counts)}
