import json

import httpx

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from app.models import SubmitRequest
from app.services import record_service
from app.services.question_service import get_exam_config, get_question_map


async def submit_exam(request: SubmitRequest, allow_ai: bool = True) -> dict:
    question_map = get_question_map()
    exam_config = get_exam_config()

    total_weighted = 0.0
    max_weighted = 0.0
    details = []
    subjective_tasks = []

    for item in request.answers:
        question = question_map.get(item.question_id)
        if not question:
            continue

        weight = question["weight"]
        max_weighted += weight * 100

        if question["type"] == "subjective":
            subjective_tasks.append((item, question, weight))
            continue

        score_rate = judge_objective(question, item.user_answer)
        item_score = round(weight * 100 * score_rate, 1)
        total_weighted += item_score

        details.append(build_detail(question, item.user_answer, score_rate >= 1.0, item_score))

    for item, question, weight in subjective_tasks:
        result = await judge_subjective(
            question["question"],
            question["answer"],
            question.get("explanation", ""),
            str(item.user_answer),
            use_ai=allow_ai,
        )
        ai_score = result["ai_score"]
        item_score = weight * ai_score
        total_weighted += item_score

        detail = build_detail(
            question,
            item.user_answer,
            ai_score >= 60,
            round(item_score, 1),
        )
        detail.update({
            "ai_score": ai_score,
            "ai_comment": result["ai_comment"],
            "ai_used": result["ai_used"],
        })
        details.append(detail)

    final_score = round(total_weighted / max_weighted * 100, 1) if max_weighted > 0 else 0
    passed = final_score >= exam_config["pass_score"]

    result = {
        "final_score": final_score,
        "passed": passed,
        "pass_score": exam_config["pass_score"],
        "details": details,
        "category_stats": build_category_stats(details),
        # 高层展示统计（assessment_category）：卡片 + 雷达图
        "assessment_stats": build_assessment_stats(details),
        # 能力维度统计（skill_dimension）：仅供 AI 总结 / 详细报告 / 能力缺陷分析
        "skill_stats": build_skill_stats(details),
        "ai_summary": await generate_ai_summary(
            final_score, passed, details, subjective_tasks, use_ai=allow_ai
        ),
    }

    if request.record_id:
        answers = [
            {"question_id": item.question_id, "user_answer": item.user_answer}
            for item in request.answers
        ]
        record_service.finish_record(request.record_id, answers, result)
        result["record_id"] = request.record_id

    return result


def judge_objective(question: dict, user_answer: str | list[str]) -> float:
    """返回得分率：1.0 全对，0.5 半对（至少对一个且无错选），0.0 错选或全错"""
    if question["type"] in ("true_false", "single_choice"):
        return 1.0 if str(user_answer).strip() == str(question["answer"]).strip() else 0.0

    if question["type"] == "multi_choice":
        user_answers = set(user_answer) if isinstance(user_answer, list) else {user_answer}
        reference_answers = set(question["answer"]) if isinstance(question["answer"], list) else {question["answer"]}

        # 全对
        if user_answers == reference_answers:
            return 1.0
        # 选了不在正确答案中的选项 → 错选，0分
        if user_answers - reference_answers:
            return 0.0
        # 没选错，但漏选了（至少还对了一个）→ 半对
        if user_answers & reference_answers:
            return 0.5
        # 全错
        return 0.0

    return 0.0


async def judge_subjective(question_text: str, reference_answer: str, explanation: str, user_answer: str, use_ai: bool = True) -> dict:
    if not DEEPSEEK_API_KEY or not use_ai:
        return fallback_judge(user_answer)

    explanation_block = f"\n【解析说明】{explanation}\n" if explanation else ""

    prompt = f"""你是一位专业的入职考核评委。请根据以下信息评判主观题答案：

【题目】{question_text}

【参考答案要点】{reference_answer}
{explanation_block}
【考生答案】{user_answer}

请从以下维度打分（0-100分）：
1. 是否覆盖核心要点
2. 逻辑是否清晰
3. 表达是否专业得体

请严格按如下JSON格式回复（不要包含其他内容）：
{{"score": 整数分数, "comment": "简短评语（50字以内）"}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                DEEPSEEK_BASE_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
            )
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            result = json.loads(content)
            return {
                "ai_score": int(result["score"]),
                "ai_comment": result.get("comment", ""),
                "ai_used": True,
            }
    except Exception as exc:
        print(f"AI grading failed: {exc}")
        return fallback_judge(user_answer)


def fallback_judge(user_answer: str) -> dict:
    keywords = ["道歉", "安抚", "升级", "记录", "跟进", "替代", "方案", "诚实", "时间", "承诺"]
    score = 0
    matched = []
    for keyword in keywords:
        if keyword in user_answer:
            score += 10
            matched.append(keyword)

    score = min(score, 80)
    if matched:
        comment = f"匹配到关键词: {', '.join(matched)}"
    else:
        comment = "未匹配到核心关键词，建议补充要点"

    return {
        "ai_score": score,
        "ai_comment": comment,
        "ai_used": False,
    }


def build_detail(
    question: dict,
    user_answer: str | list[str],
    is_correct: bool,
    score: float,
) -> dict:
    return {
        "question_id": question["id"],
        "question": question["question"],
        "category": question["category"],
        "assessment_category": question.get("assessment_category") or question["category"],
        "skill_dimensions": question.get("skill_dimension", []),
        "type": question["type"],
        "difficulty": question["difficulty"],
        "weight": question["weight"],
        "user_answer": user_answer,
        "correct_answer": question["answer"],
        "is_correct": is_correct,
        "score": score,
        "max_score": question["weight"] * 100,
        "explanation": question["explanation"],
    }


def build_category_stats(details: list[dict]) -> dict:
    category_stats = {}
    for detail in details:
        category = detail["category"]
        if category not in category_stats:
            category_stats[category] = {"score": 0, "max": 0, "correct": 0, "total": 0}

        category_stats[category]["score"] += detail["score"]
        category_stats[category]["max"] += detail["max_score"]
        category_stats[category]["total"] += 1
        if detail["is_correct"]:
            category_stats[category]["correct"] += 1

    return {
        category: {
            "correct_count": value["correct"],
            "total_count": value["total"],
            "accuracy": round(value["correct"] / value["total"] * 100, 1)
            if value["total"] > 0 else 0,
        }
        for category, value in category_stats.items()
    }


def build_assessment_stats(details: list[dict]) -> dict:
    """按 assessment_category（考试评估分类）聚合，供卡片/雷达图高层展示。"""
    stats: dict[str, dict] = {}
    for d in details:
        ac = d.get("assessment_category") or d["category"]
        s = stats.setdefault(ac, {"correct": 0, "total": 0})
        s["total"] += 1
        if d["is_correct"]:
            s["correct"] += 1
    return {
        ac: {
            "correct_count": s["correct"],
            "total_count": s["total"],
            "accuracy": round(s["correct"] / s["total"] * 100, 1)
            if s["total"] else 0,
        }
        for ac, s in stats.items()
    }


def _dimension_stats(details: list[dict]) -> dict[str, dict[str, float]]:
    """按能力维度聚合答题情况。

    优先取 detail 的 skill_dimensions；题目未打标时回退用 category。
    一道题命中多个维度时按 1/n 均摊，避免重复计数。
    """
    stats: dict[str, dict[str, float]] = {}
    for d in details:
        dims = d.get("skill_dimensions") or [d["category"]]
        share = 1.0 / len(dims)
        for dim in dims:
            s = stats.setdefault(dim, {"correct": 0.0, "total": 0.0})
            s["total"] += share
            if d["is_correct"]:
                s["correct"] += share
    return stats


def build_skill_stats(details: list[dict]) -> dict:
    """能力维度正确率统计（供雷达图使用）。"""
    return {
        dim: {
            "correct_count": round(s["correct"], 2),
            "total_count": round(s["total"], 2),
            "accuracy": round(s["correct"] / s["total"] * 100, 1)
            if s["total"] > 0 else 0,
        }
        for dim, s in _dimension_stats(details).items()
    }


async def generate_ai_summary(
    final_score: float,
    passed: bool,
    details: list[dict],
    subjective_tasks: list[tuple],
    use_ai: bool = True,
) -> str:
    """调用 AI 生成能力评估总结，失败时返回降级文本。"""
    if not DEEPSEEK_API_KEY or not use_ai:
        return _fallback_summary(final_score, passed, details)

    # 统计各能力维度正确率（无 skill_dimension 时回退到 category）
    dim_lines = []
    for dim, s in _dimension_stats(details).items():
        acc = round(s["correct"] / s["total"] * 100, 1) if s["total"] else 0
        dim_lines.append(f"- {dim}: {acc}%")
    dim_text = "\n".join(dim_lines) or "无"

    # 主观题简述
    subj_lines = []
    for item, question, _w in subjective_tasks:
        subj_lines.append(f"- 《{question['question'][:40]}...》考生答: {str(item.user_answer)[:60]}")
    subj_text = "\n".join(subj_lines) if subj_lines else "无主观题"

    prompt = f"""你是一位技术面试官。请根据考生的考核数据，用一段话（2-3句，80字以内）给出能力评估总结。

总分：{final_score} 分（及格线 60 分，{'通过' if passed else '未通过'}）

各能力维度正确率：
{dim_text}

主观题作答摘要：
{subj_text}

要求：
- 第一句说整体结论，第二句说优势方向，第三句说薄弱方向
- 语言自然，像面试官的真实点评，不要出现"雷达图""维度"这类报告话术
- 用中文，80字以内"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                DEEPSEEK_BASE_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一位资深技术面试官，擅长简洁精准地点评候选人。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 200,
                },
            )
            data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()
            # 去掉可能的引号包裹
            summary = summary.strip('"').strip("'").strip()
            return summary
    except Exception:
        return _fallback_summary(final_score, passed, details)


def _fallback_summary(final_score: float, passed: bool, details: list[dict]) -> str:
    """AI 不可用时的降级总结。"""
    dims = _dimension_stats(details)
    ranked = sorted(
        dims.items(),
        key=lambda kv: kv[1]["correct"] / kv[1]["total"] if kv[1]["total"] else 0,
    )
    strong = ranked[-1][0] if ranked else "综合"
    weak = ranked[0][0] if ranked else "综合"

    verdict = "整体表现良好" if passed else "整体表现有待提升"
    return f"该考生{verdict}，最终得分 {final_score} 分。在{strong}方面表现较好，{weak}方面仍有提升空间。"
