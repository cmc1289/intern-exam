import json

import httpx

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from app.models import SubmitRequest
from app.services import record_service
from app.services.question_service import get_exam_config, get_question_map


async def submit_exam(request: SubmitRequest) -> dict:
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
            str(item.user_answer),
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


async def judge_subjective(question_text: str, reference_answer: str, user_answer: str) -> dict:
    if not DEEPSEEK_API_KEY:
        return fallback_judge(user_answer)

    prompt = f"""你是一位专业的入职考核评委。请根据以下信息评判主观题答案：

【题目】{question_text}

【参考答案要点】{reference_answer}

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
