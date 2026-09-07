import json
import random
import tempfile
import os
import shutil

from app.config import BANK_PATH


def load_question_bank() -> dict:
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


bank = load_question_bank()
all_questions = bank["questions"]
exam_config = bank["exam_config"]
specialties = bank["specialties"]


def reload_bank() -> None:
    """重新加载题库文件到内存（AI 导入新题后热生效，无需重启）。"""
    global bank, all_questions, exam_config, specialties
    bank = load_question_bank()
    all_questions = bank["questions"]
    exam_config = bank["exam_config"]
    specialties = bank["specialties"]


def save_question_bank(data: dict) -> None:
    """原子写回题库文件；写前生成 .bak 备份，写坏不覆盖原文件。"""
    backup = str(BANK_PATH) + ".bak"
    try:
        shutil.copyfile(BANK_PATH, backup)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=str(BANK_PATH.parent), suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, BANK_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_questions(new_questions: list[dict]) -> list[dict]:
    """校验后追加题目到题库并热重载。返回带真实 id 的题目。"""
    data = load_question_bank()
    questions = data["questions"]
    used_ids = {q["id"] for q in questions}
    next_id = max(used_ids) + 1 if used_ids else 1001
    added = []
    for q in new_questions:
        q = dict(q)
        while next_id in used_ids:
            next_id += 1
        q["id"] = next_id
        next_id += 1
        used_ids.add(q["id"])
        questions.append(q)
        added.append(q)
    save_question_bank(data)
    reload_bank()
    return added


# ---- 题库目录 / 统计（供 AI 扩充与健康分析使用） ----
def bank_catalog() -> dict[str, dict]:
    """按 module 汇总可用 assessment_category 及 skill_dimension 白名单。"""
    catalog: dict[str, dict] = {}
    for q in all_questions:
        m = q["module"]
        entry = catalog.setdefault(m, {"categories": {}, "dims": set(), "total": 0})
        entry["total"] += 1
        cat = q.get("assessment_category") or q["category"] or "未分类"
        entry["categories"].setdefault(cat, 0)
        entry["categories"][cat] += 1
        for s in q.get("skill_dimension") or []:
            entry["dims"].add(s)
    out = {}
    for m, e in catalog.items():
        out[m] = {
            "total": e["total"],
            "categories": dict(sorted(e["categories"].items(), key=lambda kv: -kv[1])),
            "dims": sorted(e["dims"]),
            "ratios": exam_config.get("assessment_ratios", {}).get(m, {}),
        }
    return out


def bank_health() -> dict:
    """能力覆盖健康度：
    - 各 module 的 assessment_category 题量分布（对比 assessment_ratios 目标占比）
    - 难度分布
    - 命中配置比例但题量明显不足的维度 → 给出建议补题量
    """
    catalog = bank_catalog()
    modules = []
    for m, e in catalog.items():
        ratios = e["ratios"]
        diffs = {}
        for q in all_questions:
            if q["module"] != m:
                continue
            d = q["difficulty"]
            diffs[d] = diffs.get(d, 0) + 1
        warnings = []
        suggestions = []
        for cat, target_w in ratios.items():
            cur = e["categories"].get(cat, 0)
            # 建议补题 = 目标占比下该维度相对池子总量的合理覆盖，至少与其它维度同量级
            total_pool = e["total"]
            ideal = max(6, round(total_pool * target_w / 100))
            if cur < max(4, ideal // 3):
                need = max(4, ideal - cur)
                warnings.append(cat)
                suggestions.append(f"{cat} 当前 {cur} 题，建议补充约 {need} 道")
        modules.append({
            "module": m,
            "total": e["total"],
            "categories": e["categories"],
            "difficulty": diffs,
            "has_ratios": bool(ratios),
            "warnings": warnings,
            "suggestions": suggestions,
        })
    overall = {}
    for q in all_questions:
        d = q["difficulty"]
        overall[d] = overall.get(d, 0) + 1
    return {"modules": modules, "overall_difficulty": overall, "total_questions": len(all_questions)}


def get_exam_config() -> dict:
    return exam_config


def get_specialties() -> dict:
    return specialties


def get_questions() -> list[dict]:
    return all_questions


def get_total_question_count() -> int:
    return len(all_questions)


def get_question_map() -> dict[int, dict]:
    return {q["id"]: q for q in all_questions}


def generate_exam(
    specialty: str = "",
    min_subjective: int = 2,
    max_subjective: int = 4,
) -> dict:
    allocation = exam_config["question_allocation"]
    selected = []

    sp_list = []
    if specialty:
        sp_list = [s.strip() for s in specialty.split(",") if s.strip() in specialties]
        sp_list = sp_list[:3]

    specialty_names = ",".join(sp_list) if sp_list else ""
    sp_count = len(sp_list)
    pro_total = allocation.get("专业方向", 5)

    sp_allocation = {}
    if sp_count == 1:
        sp_allocation[sp_list[0]] = pro_total
    elif sp_count > 1:
        base = pro_total // sp_count
        remain = pro_total % sp_count
        bonus = set(random.sample(sp_list, remain))
        for s in sp_list:
            sp_allocation[s] = base + (1 if s in bonus else 0)

        # Agent 方向多分 1 题，从另一个非 Agent 方向减去
        if "Agent岗位" in sp_list:
            non_agents = [s for s in sp_list if s != "Agent岗位" and sp_allocation[s] >= 2]
            if non_agents:
                victim = random.choice(non_agents)
                sp_allocation["Agent岗位"] += 1
                sp_allocation[victim] -= 1

    module_needed = {
        "通用基础": allocation.get("通用基础", 5),
        "安全常识": allocation.get("安全常识", 2),
    }
    if sp_allocation:
        module_needed.update(sp_allocation)
    else:
        module_needed["通用基础"] += pro_total

    assessment_ratios = exam_config.get("assessment_ratios", {})

    for module, need in module_needed.items():
        module_pool = [
            q for q in all_questions
            if q["module"] == module and q not in selected
        ]
        count = min(need, len(module_pool))
        if count <= 0:
            continue
        ratios = assessment_ratios.get(module) or {}
        # 该模块配置了 assessment_category 权重 → 子方向按比例抽题
        if ratios:
            selected.extend(_pick_by_assessment_category(module_pool, count, ratios))
        # 未配置（如 Agent岗位/未打标模块）→ 保持模块内随机
        else:
            selected.extend(random.sample(module_pool, count))

    if max_subjective <= 0:
        # 不启用主观题：仅保留客观题
        selected = [q for q in selected if q["type"] != "subjective"]
    else:
        selected = ensure_subjective_range(
            selected, module_needed, min_subjective, max_subjective
        )
    random.shuffle(selected)

    questions_out = [to_public_question(q) for q in selected]

    module_dist = {}
    for q in selected:
        module = q["module"]
        module_dist[module] = module_dist.get(module, 0) + 1

    return {
        "questions": questions_out,
        "total": len(questions_out),
        "full_score": exam_config["full_score"],
        "pass_score": exam_config["pass_score"],
        "time_limit_minutes": exam_config["time_limit_minutes"],
        "specialty": specialty_names or "未选择",
        "module_distribution": module_dist,
    }


def _split_by_weights(weights: dict[str, float], total: int) -> dict[str, int]:
    """按权重把 total 拆成整数份（最大余数法，保证总和等于 total）。"""
    if total <= 0:
        return {}
    sum_w = sum(weights.values())
    if sum_w <= 0:
        return {}
    raw = {k: weights[k] * total / sum_w for k in weights}
    result = {k: int(v) for k, v in raw.items()}
    remain = total - sum(result.values())
    for k in sorted(raw, key=lambda k: raw[k] - result[k], reverse=True)[:remain]:
        result[k] += 1
    return result


def _pick_by_assessment_category(
    module_pool: list[dict],
    need: int,
    ratios: dict[str, float],
) -> list[dict]:
    """在模块池内按 assessment_category 权重抽 need 题。

    - 已配置权重 → 各子方向按比例抽
    - 权重未覆盖到、但池内存在的子方向 → 按其题量补权重，避免被永久漏抽
    - 个别子方向题量不足 → 缺口从模块其余题目补齐（绝不失败）
    """
    groups: dict[str, list[dict]] = {}
    for q in module_pool:
        ac = q.get("assessment_category") or "未分类"
        groups.setdefault(ac, []).append(q)

    weights = {c: w for c, w in ratios.items() if w > 0}
    for c, qs in groups.items():
        weights.setdefault(c, len(qs))

    targets = _split_by_weights(weights, need)
    picked: list[dict] = []
    for c, n in targets.items():
        qs = groups.get(c, [])
        if n <= 0 or not qs:
            continue
        picked.extend(random.sample(qs, min(n, len(qs))))

    # 缺口补齐（如某子方向题量不足）
    deficit = need - len(picked)
    if deficit > 0:
        chosen_ids = {id(q) for q in picked}
        rest = [q for q in module_pool if id(q) not in chosen_ids]
        picked.extend(random.sample(rest, min(deficit, len(rest))))
    return picked


def ensure_subjective_range(
    selected: list[dict],
    module_needed: dict[str, int],
    min_subjective: int = 2,
    max_subjective: int = 4,
) -> list[dict]:
    subjective_selected = [q for q in selected if q["type"] == "subjective"]
    objective_selected = [q for q in selected if q["type"] != "subjective"]
    available_subjective = [
        q for q in all_questions
        if q["type"] == "subjective"
        and q["module"] in module_needed
        and q not in selected
    ]

    # 不足：用主观题替换客观题
    deficit = max(0, min_subjective - len(subjective_selected))
    if deficit > 0:
        replace_count = min(deficit, len(available_subjective), len(objective_selected))
        if replace_count > 0:
            extra_subjective = random.sample(available_subjective, replace_count)
            return subjective_selected + extra_subjective + objective_selected[:-replace_count]

    # 过多：用客观题替换多出来的主观题
    excess = max(0, len(subjective_selected) - max_subjective)
    if excess > 0:
        available_objective = [
            q for q in all_questions
            if q["type"] != "subjective"
            and q["module"] in module_needed
            and q not in selected
        ]
        replace_count = min(excess, len(available_objective))
        if replace_count > 0:
            extra_objective = random.sample(available_objective, replace_count)
            return objective_selected + extra_objective + subjective_selected[:-replace_count]

    return selected


def to_public_question(question: dict) -> dict:
    question_out = {
        "id": question["id"],
        "module": question["module"],
        "category": question["category"],
        "type": question["type"],
        "difficulty": question["difficulty"],
        "weight": question["weight"],
        "question": question["question"],
    }
    if question["type"] in ("single_choice", "multi_choice"):
        question_out["options"] = question["options"]
    return question_out


def get_questions_by_ids(question_ids: list[int]) -> list[dict]:
    """根据 ID 列表返回题目（不含答案），保持传入顺序"""
    q_map = get_question_map()
    return [
        to_public_question(q_map[qid])
        for qid in question_ids
        if qid in q_map
    ]
