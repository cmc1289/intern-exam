# -*- coding: utf-8 -*-
"""
题库字段规范 V2.0 —— 元数据回填工具（幂等、非破坏）

作用：
  1. 按映射表给"非 Agent 岗位"模块的题目补充
     assessment_category（考试评估分类）与 skill_dimension（能力维度，数组）。
  2. 依据各模块打标后的池子构成，在 exam_config 中生成默认
     assessment_ratios（assessment_category 权重，和为 100），供智能组卷使用。
  3. Agent岗位 / 未映射题目保持原样（本轮不动），仅打印报告。

用法：
  python deploy/backfill_v2_metadata.py

安全：
  - 幂等：已带目标字段的题目不会重复写。
  - 非破坏：不改动现有字段；运行时先备份 question_bank.json.bak。
"""
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "question_bank.json"

# ---------------------------------------------------------------------------
# 映射表：module -> category -> (assessment_category, [skill_dimension, ...])
# skill_dimension 本轮先给单一主维度（数组形式，符合规范），后续可再丰富。
# ---------------------------------------------------------------------------
MAPPING: dict[str, dict[str, tuple[str, list[str]]]] = {
    # ---------------- 前端开发 ----------------
    "前端开发": {
        "HTML/CSS":     ("HTML/CSS",          ["前端基础能力"]),
        "CSS":          ("HTML/CSS",          ["前端基础能力"]),
        "JavaScript":   ("JavaScript基础",    ["前端基础能力"]),
        "TypeScript":   ("JavaScript基础",    ["前端基础能力"]),
        "前端框架":      ("框架应用",           ["工程实践能力"]),
        "框架":         ("框架应用",           ["工程实践能力"]),
        "React":        ("框架应用",           ["工程实践能力"]),
        "浏览器":        ("浏览器原理",         ["前端基础能力"]),
        "工程化":        ("工程化",             ["工程实践能力"]),
        "综合":          ("性能优化",           ["性能优化能力"]),   # 内容为前端性能优化
        "网络":          ("浏览器原理",         ["工程实践能力"]),   # 内容为跨域方案
    },
    # ---------------- 后端开发 ----------------
    "后端开发": {
        "数据库":        ("数据库",   ["数据库设计能力"]),
        "MySQL":        ("数据库",   ["数据库设计能力"]),
        "Redis":        ("缓存",     ["数据库设计能力"]),
        "缓存":         ("缓存",     ["数据库设计能力"]),
        "API设计":       ("接口设计", ["后端架构能力"]),
        "API":          ("接口设计", ["后端架构能力"]),
        "后端架构":      ("系统设计", ["后端架构能力"]),
        "架构":         ("系统设计", ["后端架构能力"]),
        "服务端":        ("数据库",   ["数据库设计能力"]),   # 内容为事务 ACID
        "认证授权":      ("安全",     ["工程规范能力"]),
        "Python":       ("语言基础", ["编码能力"]),
        "编程与框架":    ("语言基础", ["编码能力"]),   # Java 线程池/IoC/集合等
        "Python后端":   ("Web框架",  ["编码能力"]),   # FastAPI/async 等
    },
    # ---------------- 测试 ----------------
    "测试": {
        "测试基础":      ("测试理论",   ["质量意识"]),
        "测试流程":      ("测试理论",   ["质量意识"]),
        "缺陷管理":      ("测试理论",   ["质量意识"]),
        "Bug管理":      ("测试理论",   ["质量意识"]),
        "自动化测试":    ("自动化测试", ["工程能力"]),
        "自动化":        ("自动化测试", ["工程能力"]),
        "API测试":      ("接口测试",   ["测试设计能力"]),
        "性能测试":      ("性能测试",   ["工程能力"]),
        "测试方法":      ("测试设计",   ["测试设计能力"]),
    },
    # ---------------- 运维 ----------------
    "运维": {
        "Linux":       ("Linux",    ["故障排查能力"]),
        "Docker":      ("Docker",   ["部署能力"]),
        "容器":         ("Docker",   ["部署能力"]),
        "CI/CD":       ("CI/CD",    ["部署能力"]),
        "监控":         ("监控",     ["稳定性意识"]),
        "网络基础":     ("网络",     ["故障排查能力"]),
        "网络":        ("网络",     ["故障排查能力"]),
        "网络运维":     ("网络",     ["故障排查能力"]),
        "部署":        ("云部署",   ["部署能力"]),
    },
    # ---------------- 算法数据（规范未单列，建议方案） ----------------
    "算法数据": {
        "数据结构":     ("数据结构与算法", ["算法与数据结构能力"]),
        "算法":        ("数据结构与算法", ["算法与数据结构能力"]),
        "算法思想":     ("数据结构与算法", ["算法与数据结构能力"]),
        "排序算法":     ("数据结构与算法", ["算法与数据结构能力"]),
        "搜索算法":     ("数据结构与算法", ["算法与数据结构能力"]),
        "SQL":        ("SQL与数据",  ["SQL与数据处理能力"]),
        "数据库":      ("SQL与数据",  ["SQL与数据处理能力"]),
        "数据分析":     ("数据分析",   ["数据分析能力"]),
        "Python":     ("编程基础",   ["编程基础能力"]),
    },
    # ---------------- 通用基础（固定配题，打标保证雷达完整性） ----------------
    "通用基础": {
        "计算机网络":     ("计算机网络",       ["计算机网络基础"]),
        "数据结构与算法": ("数据结构与算法",   ["数据结构与算法基础"]),
        "操作系统":       ("操作系统",         ["操作系统基础"]),
        "编程基础":       ("编程基础",         ["编程基础能力"]),
    },
    # ---------------- 安全常识（固定配题，打标保证雷达完整性） ----------------
    "安全常识": {
        "Web安全":      ("Web安全",     ["安全意识"]),
        "Agent安全":    ("Agent安全",   ["安全意识"]),
        "社会工程学":    ("社会工程学",   ["安全意识"]),
        "数据安全":      ("数据安全",     ["安全意识"]),
        "密码安全":      ("密码安全",     ["安全意识"]),
        "API安全":      ("API安全",     ["安全意识"]),
        "代码安全":      ("代码安全",     ["安全意识"]),
        "认证安全":      ("认证安全",     ["安全意识"]),
        "安全架构":      ("安全架构",     ["安全意识"]),
    },
}

# ---------------------------------------------------------------------------
# Agent 岗位：category 全部为 "AI Agent"，无法按 category 机械映射，
# 故采用"题目ID 级"人工审核后的分类（见 deploy/agent_classify_suggestion.md）。
# 分类名使用规范全名，与 assessment_ratios 的 key 严格一致。
# ---------------------------------------------------------------------------

# Agent 每个 assessment_category 对应的能力维度（来自规范"能力"栏）
AGENT_SKILLS: dict[str, list[str]] = {
    "Agent基础":            ["AI基础理解能力"],
    "RAG知识增强":          ["知识增强理解能力", "AI应用设计能力"],
    "Prompt工程":           ["模型交互能力", "AI应用设计能力"],
    "Agent架构与框架":      ["Agent架构能力", "工程实践能力"],
    "Tool Calling与MCP":    ["Agent工程能力", "系统设计能力"],
    "Memory与上下文管理":    ["Agent设计能力"],
    "Agent安全":            ["安全意识", "工程规范能力"],
    "Agent工程实践":         ["工程落地能力", "系统运维能力"],
}

# Agent 岗位推荐组卷比例（规范第二节，和为 100）
AGENT_RATIOS: dict[str, int] = {
    "Agent基础": 15,
    "RAG知识增强": 20,
    "Prompt工程": 15,
    "Agent架构与框架": 15,
    "Tool Calling与MCP": 15,
    "Memory与上下文管理": 5,
    "Agent安全": 10,
    "Agent工程实践": 5,
}

# Agent 80 题分类建议（题目ID -> assessment_category）
# 依据 deploy/agent_classify_suggestion.md（已通读逐题归类）
AGENT_CATEGORY: dict[int, str] = {
    7001: "Agent基础", 7002: "Agent基础", 7003: "Agent基础",
    7010: "RAG知识增强", 7011: "Memory与上下文管理", 7012: "Tool Calling与MCP",
    7013: "Agent架构与框架", 7014: "Prompt工程", 7015: "RAG知识增强",
    7022: "Agent基础", 7023: "Agent基础", 7024: "Agent基础",
    7025: "Tool Calling与MCP", 7026: "Agent架构与框架", 7027: "Agent架构与框架",
    7029: "Agent基础", 7030: "Agent架构与框架", 7033: "Tool Calling与MCP",
    8048: "Agent基础", 8050: "Agent架构与框架", 8051: "Tool Calling与MCP",
    8100: "Agent基础", 8101: "Agent基础", 8102: "Agent基础",
    8103: "Agent基础", 8104: "Tool Calling与MCP", 8105: "Tool Calling与MCP",
    8106: "Tool Calling与MCP", 8107: "Tool Calling与MCP", 8108: "Agent架构与框架",
    8109: "Agent架构与框架", 8110: "Agent架构与框架", 8111: "Agent架构与框架",
    8112: "Memory与上下文管理", 8113: "Memory与上下文管理", 8115: "Agent基础",
    8116: "RAG知识增强", 8117: "Agent安全", 8118: "Agent基础",
    8119: "Agent工程实践", 8120: "Tool Calling与MCP", 8121: "Agent工程实践",
    8122: "Memory与上下文管理", 8123: "Agent架构与框架", 8124: "Tool Calling与MCP",
    8125: "Agent基础", 8126: "Tool Calling与MCP", 8127: "Agent基础",
    8129: "Memory与上下文管理", 8131: "Agent基础", 8132: "Memory与上下文管理",
    8134: "Tool Calling与MCP", 8135: "Tool Calling与MCP", 8136: "Agent基础",
    8137: "Tool Calling与MCP", 8138: "Agent基础", 8139: "Agent架构与框架",
    8140: "Agent基础", 8144: "Tool Calling与MCP", 8145: "Agent架构与框架",
    8150: "Agent基础", 8151: "Memory与上下文管理", 8152: "Agent基础",
    8153: "Agent基础", 8154: "Prompt工程", 8155: "RAG知识增强",
    8156: "RAG知识增强", 8157: "RAG知识增强", 8158: "RAG知识增强",
    8159: "RAG知识增强", 8160: "RAG知识增强", 8161: "Agent基础",
    8162: "Agent基础", 8163: "Tool Calling与MCP", 8164: "Tool Calling与MCP",
    8165: "Agent基础", 8166: "Agent基础", 8167: "Tool Calling与MCP",
    8168: "Tool Calling与MCP", 8169: "Tool Calling与MCP",
}

# 参与 assessment_ratios 智能组卷的模块（可被考生选择的专业方向）。
# 通用基础 / 安全常识为固定配题，不参与比例组卷。
RATIO_MODULES = ["前端开发", "后端开发", "测试", "运维", "算法数据", "Agent岗位"]
# 无待跳过模块（全部模块均完成打标）
SKIP_MODULES: set[str] = set()


def largest_remainder(weights: dict[str, int], total: int) -> dict[str, int]:
    """按权重把 total 分成整数（最大余数法，保证总和 == total）。"""
    if total <= 0:
        return {}
    sum_w = sum(weights.values())
    raw = {k: v * total / sum_w for k, v in weights.items()}
    result = {k: int(v) for k, v in raw.items()}
    remain = total - sum(result.values())
    # 余数大的优先 +1
    order = sorted(raw, key=lambda k: (raw[k] - result[k]), reverse=True)
    for k in order[:remain]:
        result[k] += 1
    return result


def derive_ratios(module: str, qs: list[dict]) -> dict[str, int]:
    """按池内各 assessment_category 的题量占比生成默认权重（和为 100）。"""
    counts: Counter = Counter(q["assessment_category"] for q in qs)
    return largest_remainder(dict(counts), 100)


def main() -> None:
    data = json.loads(BANK.read_text(encoding="utf-8"))
    questions: list[dict] = data["questions"]

    # 备份
    if not BANK.with_suffix(".json.bak").exists():
        shutil.copy2(BANK, BANK.with_suffix(".json.bak"))

    stats: dict[str, dict] = {}
    unknown: list[dict] = []
    total_updated = 0

    for q in questions:
        module = q["module"]
        if module == "Agent岗位":
            # Agent 走题目ID 级分类
            ac = AGENT_CATEGORY.get(q["id"])
            if ac is None:
                unknown.append(q)
                continue
            skills = AGENT_SKILLS[ac]
        else:
            entry = MAPPING.get(module, {}).get(q["category"])
            if entry is None:
                unknown.append(q)
                continue
            ac, skills = entry
        updated = False
        if "assessment_category" not in q:
            q["assessment_category"] = ac
            updated = True
        if "skill_dimension" not in q:
            q["skill_dimension"] = list(skills)
            updated = True
        if updated:
            total_updated += 1
        s = stats.setdefault(module, {"updated": 0, "count": 0})
        s["count"] += 1
        if updated:
            s["updated"] += 1

    # 校验：所有模块题目都必须打标成功
    missing = [q for q in questions
               if "assessment_category" not in q or "skill_dimension" not in q]
    if missing:
        print("!! 存在未打标题目：")
        for q in missing[:20]:
            print("   ", q["id"], q["module"], q["category"])
        raise SystemExit("中止：覆盖率不足，未写回。")

    # 生成 / 更新 assessment_ratios
    cfg = data.setdefault("exam_config", {})
    ratios = cfg.setdefault("assessment_ratios", {})
    ratio_report = {}
    for module in RATIO_MODULES:
        pool = [q for q in questions if q["module"] == module]
        # Agent 岗位使用规范推荐比例，其余模块默认按池子构成
        ratios[module] = (
            dict(AGENT_RATIOS) if module == "Agent岗位"
            else derive_ratios(module, pool)
        )
        ratio_report[module] = ratios[module]

    BANK.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== 回填完成 ===")
    for module, s in stats.items():
        print(f"  [{module}] 共 {s['count']} 题，本次新增 {s['updated']} 题")
    print(f"  未识别映射 {len(unknown)} 题")
    print(f"  实际写入字段的题数（含重复字段忽略）: {total_updated}")
    print("\n=== assessment_ratios ===")
    for module, r in ratio_report.items():
        note = "（Agent=规范比例，其余=按池子构成，可手工调整）" if module == "Agent岗位" else ""
        print(f"  {module}: {r} {note}")


if __name__ == "__main__":
    main()
