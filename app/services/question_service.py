import json
import random

from app.config import BANK_PATH


def load_question_bank() -> dict:
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


bank = load_question_bank()
all_questions = bank["questions"]
exam_config = bank["exam_config"]
specialties = bank["specialties"]


def get_specialties() -> dict:
    return specialties


def get_exam_config() -> dict:
    return exam_config


def get_questions() -> list[dict]:
    return all_questions


def get_total_question_count() -> int:
    return len(all_questions)


def get_question_map() -> dict[int, dict]:
    return {q["id"]: q for q in all_questions}


def generate_exam(specialty: str = "") -> dict:
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

    for module, need in module_needed.items():
        module_pool = [
            q for q in all_questions
            if q["module"] == module and q not in selected
        ]
        count = min(need, len(module_pool))
        if count > 0:
            selected.extend(random.sample(module_pool, count))

    selected = ensure_subjective_range(selected, module_needed)
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
