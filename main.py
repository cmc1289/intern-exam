import asyncio
import json
import os
import random
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="入职考核系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------- 加载题库 ---------------------
BANK_PATH = os.path.join(os.path.dirname(__file__), "question_bank.json")

with open(BANK_PATH, "r", encoding="utf-8") as f:
    bank = json.load(f)

all_questions = bank["questions"]
exam_config = bank["exam_config"]
specialties = bank["specialties"]


# --------------------- AI 主观题评判 ---------------------
AI_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
AI_API_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
AI_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


async def judge_subjective(question_text: str, reference_answer: str, user_answer: str) -> dict:
    """调用 DeepSeek API 评判主观题"""
    if not AI_API_KEY:
        # 未配置 API key 时，做简单关键词匹配
        return fallback_judge(reference_answer, user_answer)

    prompt = f"""你是一位专业的入职考核评委。请根据以下信息评判主观题答案：

【题目】{question_text}

【参考答案要点】{reference_answer}

【考生答案】{user_answer}

请从以下维度打分（0-100分）：
1. 是否覆盖核心要点
2. 逻辑是否清晰
3. 表述是否专业得体

请严格按如下JSON格式回复（不要包含其他内容）：
{{"score": 整数分数, "comment": "简短评语（50字以内）"}}"""

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                AI_API_URL,
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # 清理可能的 markdown 代码块包裹
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
    except Exception as e:
        print(f"AI 评判异常: {e}")
        return fallback_judge(reference_answer, user_answer)


def fallback_judge(reference: str, user_answer: str) -> dict:
    """无 AI 时的关键词兜底评判"""
    keywords = ["道歉", "安抚", "升级", "记录", "跟进", "替代", "方案", "诚实", "时间", "承诺"]
    score = 0
    matched = []
    for kw in keywords:
        if kw in user_answer:
            score += 10
            matched.append(kw)
    score = min(score, 80)
    comment = f"匹配到关键词: {', '.join(matched)}" if matched else "未匹配到核心关键词，建议补充要点"
    return {"ai_score": score, "ai_comment": comment, "ai_used": False}


# --------------------- API Models ---------------------
class AnswerItem(BaseModel):
    question_id: int
    user_answer: str | list[str]


class SubmitRequest(BaseModel):
    answers: list[AnswerItem]


# --------------------- 路由 ---------------------
@app.get("/api/specialties")
async def get_specialties():
    """返回可选专业方向列表"""
    return {"specialties": specialties}


@app.get("/api/exam/start")
async def start_exam(specialty: str = ""):
    """根据专业方向随机抽取题目组成试卷，保证至少2道主观题。specialty 支持逗号分隔多选（1~3个）"""
    allocation = exam_config["question_allocation"]
    selected = []

    # 解析多专业选择
    sp_list = []
    if specialty:
        sp_list = [s.strip() for s in specialty.split(",") if s.strip() in specialties]
        sp_list = sp_list[:3]  # 最多3个

    specialty_names = ",".join(sp_list) if sp_list else ""
    sp_count = len(sp_list)
    pro_total = allocation.get("专业方向", 5)

    # 计算各专业的分配数量
    sp_allocation = {}
    if sp_count == 0:
        pass  # 未选方向，名额给通用基础
    elif sp_count == 1:
        sp_allocation[sp_list[0]] = pro_total
    else:
        # 2~3 个方向：均匀+随机余数分配
        base = pro_total // sp_count
        remain = pro_total % sp_count
        # 随机挑 remain 个方向各多分1题
        bonus = set(random.sample(sp_list, remain))
        for s in sp_list:
            sp_allocation[s] = base + (1 if s in bonus else 0)

    # 按模块分配名额
    module_needed = {
        "通用基础": allocation.get("通用基础", 7),
        "安全常识": allocation.get("安全常识", 2),
    }
    if sp_allocation:
        module_needed.update(sp_allocation)
    else:
        module_needed["通用基础"] += pro_total

    # -- 按模块随机抽取（每题概率均等，主观题自然参与） --
    for mod, need in module_needed.items():
        mod_pool = [q for q in all_questions if q["module"] == mod and q not in selected]
        count = min(need, len(mod_pool))
        if count > 0:
            selected.extend(random.sample(mod_pool, count))

    # -- 保证至少2道主观题 --
    subj_selected = [q for q in selected if q["type"] == "subjective"]
    obj_selected = [q for q in selected if q["type"] != "subjective"]
    min_subj = 2
    deficit = max(0, min_subj - len(subj_selected))
    if deficit > 0:
        # 收集所有可用模块中未被选中的主观题
        available_subj = [q for q in all_questions
                          if q["type"] == "subjective"
                          and q["module"] in module_needed
                          and q not in selected]
        needed = min(deficit, len(available_subj))
        if needed > 0:
            # 用主观题替换末尾的客观题
            extra_subj = random.sample(available_subj, needed)
            selected = subj_selected + extra_subj + obj_selected[:-needed]

    # 打乱顺序
    random.shuffle(selected)

    # 返回题目（不含答案）
    questions_out = []
    for q in selected:
        q_out = {
            "id": q["id"],
            "module": q["module"],
            "category": q["category"],
            "type": q["type"],
            "difficulty": q["difficulty"],
            "weight": q["weight"],
            "question": q["question"],
        }
        if q["type"] in ("single_choice", "multi_choice"):
            q_out["options"] = q["options"]
        questions_out.append(q_out)

    module_dist = {}
    for q in selected:
        m = q["module"]
        module_dist[m] = module_dist.get(m, 0) + 1

    return {
        "questions": questions_out,
        "total": len(questions_out),
        "full_score": exam_config["full_score"],
        "pass_score": exam_config["pass_score"],
        "time_limit_minutes": exam_config["time_limit_minutes"],
        "specialty": specialty_names,
        "module_distribution": module_dist,
    }


@app.post("/api/exam/submit")
async def submit_exam(req: SubmitRequest):
    """提交答案并判分"""
    # 建立 id -> question 映射
    q_map = {q["id"]: q for q in all_questions}

    total_weighted = 0.0
    max_weighted = 0.0
    details = []
    subjective_tasks = []

    for item in req.answers:
        q = q_map.get(item.question_id)
        if not q:
            continue

        weight = q["weight"]
        max_weighted += weight * 100  # 每题满分 100（加权后）

        if q["type"] == "subjective":
            # 主观题：异步评判
            subjective_tasks.append((item, q, weight))
            continue

        # 客观题直接判断
        correct = False
        if q["type"] == "true_false":
            correct = (item.user_answer.strip() == q["answer"].strip())
        elif q["type"] == "single_choice":
            correct = (item.user_answer.strip() == q["answer"].strip())
        elif q["type"] == "multi_choice":
            user_ans = item.user_answer if isinstance(item.user_answer, list) else [item.user_answer]
            ref_ans = q["answer"] if isinstance(q["answer"], list) else [q["answer"]]
            correct = set(user_ans) == set(ref_ans)

        item_score = weight * 100 if correct else 0
        total_weighted += item_score

        details.append({
            "question_id": q["id"],
            "question": q["question"],
            "category": q["category"],
            "type": q["type"],
            "difficulty": q["difficulty"],
            "weight": weight,
            "user_answer": item.user_answer,
            "correct_answer": q["answer"],
            "is_correct": correct,
            "score": item_score,
            "max_score": weight * 100,
            "explanation": q["explanation"],
        })

    # 处理主观题
    for item, q, weight in subjective_tasks:
        result = await judge_subjective(q["question"], q["answer"], item.user_answer)
        ai_score = result["ai_score"]
        item_score = weight * ai_score
        total_weighted += item_score

        details.append({
            "question_id": q["id"],
            "question": q["question"],
            "category": q["category"],
            "type": q["type"],
            "difficulty": q["difficulty"],
            "weight": weight,
            "user_answer": item.user_answer,
            "correct_answer": q["answer"],
            "is_correct": ai_score >= 60,
            "score": round(item_score, 1),
            "max_score": weight * 100,
            "explanation": q["explanation"],
            "ai_score": ai_score,
            "ai_comment": result["ai_comment"],
            "ai_used": result["ai_used"],
        })

    # 换算为百分制
    if max_weighted > 0:
        final_score = round(total_weighted / max_weighted * 100, 1)
    else:
        final_score = 0

    passed = final_score >= exam_config["pass_score"]

    # 按类别统计
    category_stats = {}
    for d in details:
        cat = d["category"]
        if cat not in category_stats:
            category_stats[cat] = {"score": 0, "max": 0, "correct": 0, "total": 0}
        category_stats[cat]["score"] += d["score"]
        category_stats[cat]["max"] += d["max_score"]
        category_stats[cat]["total"] += 1
        if d["is_correct"]:
            category_stats[cat]["correct"] += 1

    return {
        "final_score": final_score,
        "passed": passed,
        "pass_score": exam_config["pass_score"],
        "details": details,
        "category_stats": {
            cat: {
                "correct_count": v["correct"],
                "total_count": v["total"],
                "accuracy": round(v["correct"] / v["total"] * 100, 1) if v["total"] > 0 else 0,
            }
            for cat, v in category_stats.items()
        },
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "total_questions": len(all_questions)}


# --------------------- 挂载前端静态文件 ---------------------
static_path = os.path.dirname(__file__)
if os.path.isfile(os.path.join(static_path, "index.html")):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
