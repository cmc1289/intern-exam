"""题库智能扩充（AI 辅助）核心服务。

流程（遵循《题库智能扩充与评估模型优化需求文档 V1.0》）：
  1) 候选收集：给定领域话题，AI 脑暴候选问题；若提供 URL，尽力抓取单页文本后让 AI 抽取问题。
  2) 筛选：AI 剔除太偏/太难/与评估无关的候选，标注保留与理由。
  3) 知识点聚合：把保留候选归类为知识点，并映射到该 module 的 assessment_category / skill_dimension 白名单。
  4) 重新设计：不保存原题，按评估目的生成新的标准题（单选/多选/判断/主观 + 答案/解析/难度/打标）。
  5) 入库：append_questions + 热重载；dry_run 仅预览不写库。

设计约束：
  - 白名单驱动：assessment_category / skill_dimension 只能取题库现有覆盖值（避免产生无法组卷/画像的孤儿维度）。
  - 结果强校验：题目必须满足 schema，失败条目给出原因。
"""
import asyncio
import difflib
import json
import re
import time
import uuid

import httpx

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from app.services.question_service import append_questions, bank_catalog

AI_TIMEOUT = 180
DIFF_WEIGHT = {"简单": 1.0, "中等": 1.5, "困难": 2.0}
VALID_TYPES = {"single_choice", "multi_choice", "true_false", "subjective"}


# ---------------- 题库健康概览 / 用户指令解析 ----------------
def _health_snapshot(module: str) -> str:
    """生成该方向的健康概览文本（各维度现有题量 + 建议补题量），注入 AI 供其控制总量。"""
    try:
        catalog = bank_catalog()
    except Exception:
        return ""
    m = catalog.get(module)
    if not m:
        return ""
    ratios = m.get("ratios") or {}
    total = m.get("total", 0)
    lines = []
    cats = list(m.get("categories", {}).keys())
    # 有配置比例的维度排前面（它们才是组卷真正关心的口径）
    ordered = sorted(cats, key=lambda c: (c in ratios, -m["categories"][c]), reverse=True)
    for c in ordered:
        cur = m["categories"].get(c, 0)
        w = ratios.get(c)
        if w:
            ideal = max(6, round(total * w / 100))
            need = max(0, ideal - cur)
            note = f"，建议本轮补 {need} 道" if need > 0 else "，暂够用"
            lines.append(f"- {c}：现有 {cur} 题（组卷目标占比 {w}%，建议规模 {ideal}）{note}")
        else:
            lines.append(f"- {c}：现有 {cur} 题（未配置组卷占比）")
    return "\n".join(lines)


def _parse_count_instruction(instruction: str) -> int | None:
    """从用户说明中提取明确的补题数量，如“补 5 道”“5~8 道”“控制 10 题以内”。返回目标数或 None。"""
    if not instruction:
        return None
    text = instruction.strip()
    m = re.search(r"(\d{1,2})\s*[-~到至]\s*(\d{1,2})\s*道", text)  # 范围取下界
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"(\d{1,2})\s*[道题个]", text)
    if m:
        return max(1, int(m.group(1)))
    return None


def _fuzzy_map(value: str, whitelist: list[str]) -> str | None:
    """把 AI 可能写出的近似维度名归一化到白名单（如 数据结构/链表 → 数据结构与算法）。

    规则：精确匹配 > 互相包含 > 编辑距离相似 > 字符包含。
    """
    v = (value or "").strip()
    if not v or not whitelist:
        return None
    if v in whitelist:
        return v
    # 互相包含（短词放两边都试）
    for w in whitelist:
        if v in w or w in v:
            return w
    # 去空格后的包含（如 "数据结构与算法" vs "数据结构算法"）
    flat_v = re.sub(r"[与和及、/·\s]", "", v)
    for w in whitelist:
        flat_w = re.sub(r"[与和及、/·\s]", "", w)
        if flat_v in flat_w or flat_w in flat_v:
            return w
    # 编辑距离
    best = difflib.get_close_matches(v, whitelist, n=1, cutoff=0.5)
    if best:
        return best[0]
    return None

# 内存任务表：{job_id: {id, module, dry_run, status, stage, result, error, created_at, updated_at}}
_jobs: dict[str, dict] = {}
_jobs_lock = asyncio.Lock()


async def _job_set(job_id: str, **kw) -> None:
    async with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kw)
            _jobs[job_id]["updated_at"] = time.time()


async def start_expand_job(
    module: str,
    topics: list[str],
    urls: list[str] | None,
    dry_run: bool,
    instruction: str = "",
    mode: str = "brainstorm",
) -> dict:
    """创建异步扩充任务并立即返回 job_id。mode: brainstorm=快速脑暴 / url=URL 定向。"""
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "id": job_id,
        "module": module,
        "dry_run": dry_run,
        "instruction": instruction,
        "mode": mode,
        "status": "pending",
        "stage": "排队中",
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    asyncio.create_task(_run_job(job_id, module, topics, urls, dry_run, instruction, mode))
    return {"job_id": job_id, "status": "running"}


def get_job(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    if not job:
        return None
    return {
        "id": job["id"],
        "module": job["module"],
        "dry_run": job["dry_run"],
        "instruction": job.get("instruction", ""),
        "mode": job.get("mode", "brainstorm"),
        "status": job["status"],
        "stage": job.get("stage", ""),
        "result": job["result"],
        "error": job.get("error"),
    }


async def _run_job(
    job_id: str,
    module: str,
    topics: list[str],
    urls: list[str] | None,
    dry_run: bool,
    instruction: str = "",
    mode: str = "brainstorm",
) -> None:
    stage_name = "候选收集"
    try:
        await _job_set(job_id, status="running", stage="候选收集…")
        result = await run_expansion(
            module, topics, urls, instruction=instruction, dry_run=dry_run, mode=mode
        )
        await _job_set(job_id, status="done", stage="完成", result=result)
    except ExpansionError as exc:
        await _job_set(job_id, status="error", stage="失败", error=f"【{stage_name}阶段】{exc}")
    except Exception as exc:  # noqa: BLE001
        await _job_set(job_id, status="error", stage="失败", error=f"【{stage_name}阶段】AI 扩充失败：{exc}")


class ExpansionError(Exception):
    pass


# ---------------- AI 调用 ----------------
async def _chat(system: str, user: str, max_tokens: int = 4000) -> str:
    if not DEEPSEEK_API_KEY:
        raise ExpansionError("未配置 DEEPSEEK_API_KEY，无法使用 AI 扩充题库")
    async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
        resp = await client.post(
            DEEPSEEK_BASE_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.7,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # 去 ```json ... ``` 包裹
        fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
        if fence:
            content = fence.group(1).strip()
        return content


def _parse_json(content: str):
    if not content or not content.strip():
        raise ExpansionError("AI 返回内容为空")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 尝试截取第一个 [ 或 { 到最后一个 } / ]
        for a, b in (("[", "]"), ("{", "}")):
            s, e = content.find(a), content.rfind(b)
            if s != -1 and e > s:
                try:
                    return json.loads(content[s : e + 1])
                except json.JSONDecodeError:
                    continue
        raise ExpansionError(f"AI 返回内容无法解析为 JSON：{content[:200]}")


async def _ask_json(system: str, user: str, max_tokens: int = 4000, retries: int = 3) -> dict:
    """带重试的 JSON 请求：网络抖动或偶发坏 JSON 时重试。"""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            content = await _chat(system, user, max_tokens=max_tokens)
            return _parse_json(content)
        except Exception as exc:  # noqa: BLE001 - 转重试
            last_exc = exc
            if attempt < retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
    if isinstance(last_exc, ExpansionError):
        raise last_exc
    raise ExpansionError(f"AI 请求多次失败：{last_exc}")


# ---------------- 网页抓取（尽力而为） ----------------
async def _fetch_page_text(url: str, timeout: int = 12) -> str:
    """抓取单页并粗提取正文纯文本。失败抛异常由上层兜底。"""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        resp.raise_for_status()
    html = resp.text
    # 去脚本/样式/标签
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;?", " ", html)
    html = re.sub(r"&#?\w+;", " ", html)
    text = re.sub(r"[ \t]+", " ", html)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)[:8000]


async def collect_candidates(
    module: str,
    topics: list[str],
    urls: list[str] | None = None,
    instruction: str = "",
) -> dict:
    """候选收集：URL 文本（可选） + AI 脑暴候选问题。返回 {candidates, sources}。"""
    sources = []
    page_texts = []
    for url in (urls or [])[:3]:
        try:
            txt = await _fetch_page_text(url)
            if txt:
                page_texts.append(txt)
                sources.append({"url": url, "chars": len(txt)})
        except Exception as exc:
            sources.append({"url": url, "error": str(exc)[:120]})

    topic_text = "\n".join(f"- {t}" for t in topics if t.strip())
    extra = ""
    if page_texts:
        extra = "\n\n【网页素材】\n" + "\n\n---\n\n".join(page_texts)
    user_note = f"\n【用户补充要求】{instruction}\n" if instruction.strip() else ""

    sys_p = (
        "你是资深的技术面试官和题库设计师。你会被要求围绕特定方向生成候选面试问题。"
        "只输出 JSON，格式：{\"candidates\":[{\"question\":\"...\",\"topic\":\"...\"}]}"
    )
    user = (
        f"专业方向：{module}\n待覆盖话题：\n{topic_text or '（通用，覆盖该方向主干知识点）'}"
        f"{extra}{user_note}\n"
        "请列出 15~25 个该方向真正有价值的候选面试问题（宁缺毋滥），"
        "涵盖概念理解、原理分析、场景设计三个层次，不要重复。"
        "如用户补充要求提到聚焦维度或难度偏好，请优先遵守。"
    )
    data = await _ask_json(sys_p, user, max_tokens=12000)
    candidates = []
    for c in data.get("candidates", [])[:30]:
        q = (c.get("question") or "").strip()
        if len(q) >= 6:
            candidates.append({"question": q, "topic": (c.get("topic") or topics[0] if topics else "").strip()})
    return {"candidates": candidates, "sources": sources, "count": len(candidates)}


async def screen_candidates(module: str, candidates: list[dict]) -> dict:
    """AI 筛选：剔除过难/与岗位评估无关的候选。返回保留列表 + 说明。"""
    if not candidates:
        return {"kept": [], "dropped": [], "summary": "无候选"}

    def _sum(cs):
        return "\n".join(f"{i + 1}. {c['question']}" for i, c in enumerate(cs))

    sys_p = (
        "你是技术招聘题库把关人。考生为初级/实习候选人与中级工程师，评估目标是判断基础与潜力，"
        "而不是刁难。只输出 JSON：{\"keep\":[编号],\"drop\":[编号],\"reason\":\"一句话说明\"}"
    )
    user = (
        f"专业方向：{module}\n以下候选问题哪些适合纳入评估？请剔除过难/过于冷门八股/与岗位能力无关的。\n"
        f"{_sum(candidates)}"
    )
    data = await _ask_json(sys_p, user, max_tokens=8000)
    keep_ids = {int(i) for i in data.get("keep", [])}
    kept, dropped = [], []
    for idx, c in enumerate(candidates, start=1):
        if idx in keep_ids:
            kept.append(c)
        else:
            dropped.append({"question": c["question"], "reason": data.get("reason", "未通过筛选")})
    return {"kept": kept, "dropped": dropped, "summary": f"保留 {len(kept)} / {len(candidates)}"}


async def cluster_knowledge(
    module: str,
    candidates: list[dict],
    instruction: str = "",
    has_url_source: bool = False,
) -> dict:
    """知识点聚合 + 维度映射。返回知识点列表（assessment_category / skill_dimension 从白名单取）。"""
    catalog = bank_catalog()
    m = catalog.get(module)
    if not m:
        raise ExpansionError(f"题库中不存在方向「{module}」，可选：{', '.join(catalog.keys())}")
    cat_whitelist = list(m["categories"].keys())
    dim_whitelist = m["dims"] or []
    health = _health_snapshot(module)
    target = _parse_count_instruction(instruction)
    user_note = f"\n【用户补充要求】{instruction}\n" if instruction.strip() else ""
    if target:
        target_note = (
            f"\n【本轮补题总量目标】请让各知识点 question_count 之和尽量贴近 {target} 道，不超过 {target} 道；宁可少于目标，也不要明显超过。"
        )
    elif has_url_source:
        # 用户给了具体参考页 = 定向补充，健康概览仅供参考，不做“已够用就少加”的压制
        target_note = (
            "\n【本轮补题总量】本次有用户指定的参考页面（定向补充），请为每个知识点正常配置 1~3 道、"
            "合计控制在 3~10 道；健康概览仅用于提示可选优先维度，不要把已够用的维度压成 0 或 1 道。"
        )
    else:
        target_note = "\n【补题总量约束】question_count 之和请不要超过健康概览中“建议补”的总缺口；缺多少补多少，不要制造过剩。"

    def _sum(cs):
        return "\n".join(f"{i + 1}. {c['question']}" for i, c in enumerate(cs))

    sys_p = (
        "你是题库结构设计师。把候选问题聚合为若干知识点，并映射到给定维度的白名单。"
        "只输出 JSON：{\"knowledge_points\":[{\"name\":\"知识点名\",\"assessment_category\":\"...\","
        "\"skill_dimension\":[\"...\"],\"related\":[候选编号],\"question_count\":期望生成题数}]}"
    )
    user = (
        f"专业方向：{module}\n可选 assessment_category：{json.dumps(cat_whitelist, ensure_ascii=False)}\n"
        f"可选 skill_dimension：{json.dumps(dim_whitelist, ensure_ascii=False)}\n"
        f"{user_note}"
        f"\n【当前题库健康概览（参考）】\n{health}\n"
        "请把候选问题聚类为 3~8 个知识点。每个知识点必须映射到上面的 assessment_category 白名单之一"
        "（若候选在“数据结构/链表/哈希表”等，请归一映射到白名单中最接近的维度，如“数据结构与算法”）；"
        "skill_dimension 尽量匹配该方向现有维度；related 填对应候选编号；"
        "question_count 为该知识点希望生成的新题数（1~3）。"
        f"{target_note}"
        f"\n候选问题：\n{_sum(candidates)}"
    )
    data = await _ask_json(sys_p, user, max_tokens=16000)
    kps = data.get("knowledge_points", [])

    out = []
    dropped = []
    for kp in kps:
        raw_ac = (kp.get("assessment_category") or "").strip()
        ac = _fuzzy_map(raw_ac, cat_whitelist)
        if ac is None:
            dropped.append(f"知识点「{kp.get('name') or raw_ac}」维度「{raw_ac}」无法映射到现有维度，已跳过")
            continue
        sd = []
        for s in (kp.get("skill_dimension") or []):
            mapped = _fuzzy_map(s, dim_whitelist)
            if mapped and mapped not in sd:
                sd.append(mapped)
        out.append({
            "name": (kp.get("name") or ac).strip()[:40],
            "assessment_category": ac,
            "skill_dimension": sd[:2],
            "question_count": min(max(int(kp.get("question_count") or 1), 1), 3),
        })
    if not out:
        raise ExpansionError(
            "AI 未聚合出可映射的知识点（全部落到白名单之外）：" + ("；".join(dropped[:3]) or "无")
        )
    # 去重合并同维度同名的知识点，避免生成碎片
    merged: dict[tuple, dict] = {}
    for k in out:
        key = (k["assessment_category"], k["name"])
        if key in merged:
            merged[key]["question_count"] = min(merged[key]["question_count"] + k["question_count"], 3)
        else:
            merged[key] = dict(k)
    out = list(merged.values())

    # 硬上限：用户明确说补 N 道则截断到 N；URL 定向补充上限 10；纯脑暴按健康缺口封顶 12
    if target:
        cap = min(target, 12)
    elif has_url_source:
        cap = 10
    else:
        cap = 12
    # 先保每个知识点 1 题，剩余额度按序分配，确保覆盖面
    base = [k for k in out]
    assigned = {i: 0 for i in range(len(base))}
    remaining = cap
    for _round in range(3):
        for i, k in enumerate(base):
            if remaining <= 0:
                break
            if assigned[i] < min(k["question_count"], 3):
                assigned[i] += 1
                remaining -= 1
        if remaining <= 0:
            break
    planned = [dict(k, question_count=assigned[i]) for i, k in enumerate(base)]
    planned = [k for k in planned if k["question_count"] > 0]
    total = min(sum(k["question_count"] for k in planned), cap)
    return {"knowledge_points": planned[:8], "planned_total": total, "dropped": dropped}


async def design_questions(module: str, knowledge_points: list[dict], instruction: str = "") -> dict:
    """重新设计题目：按知识点生成标准题（不保存原题），白名单打标 + 强 schema。"""
    catalog = bank_catalog()
    m = catalog[module]
    cat_whitelist = list(m["categories"].keys())
    dim_whitelist = m["dims"] or []
    user_note = f"\n【用户补充要求】{instruction}\n" if instruction.strip() else ""

    sys_p = (
        "你是资深题库设计师。请根据知识点重新设计标准考核题，而不是照搬任何网络原题。"
        "题型：单选 single_choice / 多选 multi_choice / 判断 true_false / 主观 subjective，混合搭配。"
        "只输出 JSON：{\"questions\":[{...}]}，每题字段："
        "{\"question\":\"题干\",\"type\":\"single_choice\",\"options\":[\"A\",\"B\",\"C\",\"D\"]"
        ",\"answer\":\"正确选项文本或数组\",\"explanation\":\"解析\",\"difficulty\":\"简单|中等|困难\","
        "\"assessment_category\":\"...\",\"skill_dimension\":[\"...\"]}"
    )
    kp_lines = []
    for kp in knowledge_points:
        kp_lines.append(
            f"- 知识点：{kp['name']}｜要生成 {kp['question_count']} 题｜"
            f"assessment_category 应取白名单 {json.dumps(kp['assessment_category'], ensure_ascii=False)}"
        )
    user = (
        f"专业方向：{module}\nassessment_category 白名单：{json.dumps(cat_whitelist, ensure_ascii=False)}\n"
        f"skill_dimension 白名单：{json.dumps(dim_whitelist, ensure_ascii=False)}\n"
        f"{user_note}"
        f"难度与场景要求：客观题偏概念/原理，主观题偏设计与排查；困难题可为设计题。\n"
        "请严格按上面每个知识点标明的题量生成题目，不要超量（超出的题不会入库）。"
        "（每个知识点的 assessment_category 必须落到白名单；"
        "单选的 answer 必须是 options 之一，多选 answer 是选项数组，判断 answer 为 正确/错误）：\n"
        + "\n".join(kp_lines)
    )
    data = await _ask_json(sys_p, user, max_tokens=16000)
    raw = data.get("questions", [])[:16]
    validated, errors = _validate_questions(module, raw)
    return {"questions": validated, "errors": errors, "count": len(validated)}


def _validate_questions(module: str, raw: list[dict]) -> tuple[list[dict], list[str]]:
    catalog = bank_catalog()
    m = catalog.get(module, {})
    cat_whitelist = list(m.get("categories", {}).keys())
    dim_whitelist = list(m.get("dims", []))
    cat_ok = set(cat_whitelist)
    dim_ok = set(dim_whitelist)

    validated = []
    errors = []
    for idx, q in enumerate(raw, start=1):
        try:
            qtype = q.get("type")
            if qtype not in VALID_TYPES:
                raise ValueError(f"非法题型 {qtype}")
            question = str(q.get("question") or "").strip()
            if len(question) < 8:
                raise ValueError("题干过短")
            difficulty = q.get("difficulty")
            if difficulty not in DIFF_WEIGHT:
                difficulty = "中等"
            raw_ac = (q.get("assessment_category") or "").strip()
            ac = _fuzzy_map(raw_ac, cat_whitelist)
            if ac is None:
                raise ValueError(f"assessment_category「{raw_ac}」不在白名单")
            sd = []
            for s in (q.get("skill_dimension") or []):
                mapped = _fuzzy_map(s, dim_whitelist)
                if mapped and mapped not in sd:
                    sd.append(mapped)
            answer = q.get("answer")
            explanation = str(q.get("explanation") or "").strip()

            out = {
                "module": module,
                "category": ac,
                "assessment_category": ac,
                "skill_dimension": sd[:2],
                "type": qtype,
                "difficulty": difficulty,
                "weight": DIFF_WEIGHT[difficulty],
                "question": question,
                "explanation": explanation,
            }

            if qtype == "single_choice":
                opts = [str(o) for o in (q.get("options") or []) if str(o).strip()]
                if len(opts) < 2 or answer not in opts:
                    raise ValueError("单选需 2+ 选项且答案在选项中")
                out["options"] = opts
                out["answer"] = answer
            elif qtype == "multi_choice":
                opts = [str(o) for o in (q.get("options") or []) if str(o).strip()]
                ans = answer if isinstance(answer, list) else [answer]
                if len(opts) < 2 or not ans or not all(a in opts for a in ans):
                    raise ValueError("多选答案必须是选项数组且均命中选项")
                out["options"] = opts
                out["answer"] = ans
            elif qtype == "true_false":
                if answer not in ("正确", "错误"):
                    raise ValueError("判断题 answer 必须为 正确/错误")
                out["answer"] = answer
            else:  # subjective
                if not explanation:
                    raise ValueError("主观题缺答案解析要点")
                out["answer"] = str(answer or "")[:400]

            validated.append(out)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"候选 {idx} 被拒：{exc}")
    return validated, errors


async def run_expansion(
    module: str,
    topics: list[str],
    urls: list[str] | None = None,
    instruction: str = "",
    dry_run: bool = False,
    mode: str = "brainstorm",
) -> dict:
    """主流程：候选收集 → 筛选 → 聚合 → 重设计 → 入库。

    mode=brainstorm：纯 AI 脑暴（忽略 URL，最快）；
    mode=url：抓取参考页清洗后出题，抓取失败明确报错，不静默回退脑暴。
    """
    if not DEEPSEEK_API_KEY:
        raise ExpansionError("未配置 DEEPSEEK_API_KEY，无法使用 AI 扩充题库")

    if mode not in ("brainstorm", "url"):
        mode = "brainstorm"
    if mode == "url" and not (urls and any(u.strip() for u in urls)):
        raise ExpansionError("URL 模式必须至少提供一个参考 URL")
    if mode == "brainstorm":
        urls = None  # 快速模式不抓取任何页面

    catalog = bank_catalog()
    if module not in catalog:
        raise ExpansionError(f"题库中不存在方向「{module}」，可选：{', '.join(catalog.keys())}")

    try:
        collected = await collect_candidates(module, topics, urls, instruction=instruction)
    except ExpansionError:
        raise
    except Exception as exc:
        raise ExpansionError(f"候选收集失败：{exc}") from exc
    if not collected["candidates"]:
        raise ExpansionError("未收集到候选问题（请确认话题或 URL 可用）")
    if mode == "url":
        ok_sources = [s for s in collected.get("sources", []) if s.get("chars")]
        if not ok_sources:
            errs = "；".join(s.get("error", "未知错误") for s in collected.get("sources", []))
            raise ExpansionError(f"参考 URL 全部抓取失败，未回退到脑暴：{errs}")

    try:
        screened = await screen_candidates(module, collected["candidates"])
    except ExpansionError:
        raise
    except Exception as exc:
        raise ExpansionError(f"候选筛选失败：{exc}") from exc
    if not screened["kept"]:
        raise ExpansionError(f"候选均未通过筛选：{screened['summary']}")

    try:
        clustered = await cluster_knowledge(
            module,
            screened["kept"],
            instruction=instruction,
            has_url_source=(mode == "url"),
        )
    except ExpansionError:
        raise
    except Exception as exc:
        raise ExpansionError(f"知识点聚合失败：{exc}") from exc

    try:
        designed = await design_questions(module, clustered["knowledge_points"], instruction=instruction)
    except ExpansionError:
        raise
    except Exception as exc:
        raise ExpansionError(f"题目重设计失败：{exc}") from exc

    # 硬性防失衡：入库/预览量不得超过规划总量（用户"补 N 道"或健康缺口）
    planned_total = clustered["planned_total"]
    questions = designed["questions"][:planned_total] if planned_total else designed["questions"]
    truncated = max(0, len(designed["questions"]) - len(questions))
    errors = list(designed["errors"])
    errors.extend(clustered.get("dropped") or [])
    if truncated:
        errors.append(f"已截断超出规划总量的 {truncated} 道（规划 {planned_total} 道），避免比例失衡")

    if dry_run:
        return {
            "dry_run": True,
            "module": module,
            "collected_count": collected["count"],
            "sources": collected["sources"],
            "screen": screened["summary"],
            "knowledge_points": clustered["knowledge_points"],
            "planned_total": clustered["planned_total"],
            "questions": questions,
            "errors": errors,
            "inserted_count": 0,
        }

    if not questions:
        raise ExpansionError(f"AI 生成题目全部未通过校验：{'；'.join(errors)}")

    added = append_questions(questions)
    return {
        "dry_run": False,
        "module": module,
        "collected_count": collected["count"],
        "sources": collected["sources"],
        "screen": screened["summary"],
        "knowledge_points": clustered["knowledge_points"],
        "planned_total": clustered["planned_total"],
        "questions": questions,
        "errors": errors,
        "inserted_count": len(added),
        "new_ids": [q["id"] for q in added],
    }
