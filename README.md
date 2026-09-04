# 入职考核系统 · 智能技术能力评估平台

一套**个人自测 + 组织化招聘双模式**的技术能力评估平台：候选人在线答题，客观题自动判分、主观题由 DeepSeek 进行 AI 批改，最终输出按能力维度（能力卡片 / 雷达图）的成绩单与 AI 评估总结。既支持个人随时自测，也支持管理员建考试、发邀请码、组织批量候选人测评与归档。

## 功能概览

### 双模式
- **个人自测（public）** — 首页直接选择 1~3 个专业方向开始答题，成绩按浏览器本地 `visitor_id` 归档，仅自己可见。
- **组织化考试（exam）** — 管理员创建考试并生成**邀请码**，候选人凭 `/exam/join?code=XXX` + 姓名进入；同一位候选人同一场考试**仅一次作答机会**。

### 组卷与答题
- **按比例智能组卷** — 通用基础 4 题 + 专业方向 14 题 + 安全常识 2 题，共 20 题；多选方向时按比例分摊、Agent 方向自动 +1 题。
- **子方向分层抽题** — 已打标模块按 `assessment_category` 权重抽题（如 Agent 岗位按 Agent基础/RAG/Prompt/架构/工具调用等比例），未打标模块池内随机。
- **客观题即时判定** — 单选、多选、判断题由后端直接比对答案；多选题**部分给分**（全对满分，有正确但无错误半对给 50%，错选 0 分）。
- **主观题 AI 批改** — 接入 DeepSeek，Prompt 携带题目、参考答案要点、答案解析、考生答案四元约束做语义评判并给出评语。
- **难度加权计分** — 简单 ×1.0 / 中等 ×1.5 / 困难 ×2.0，按加权得分换算百分制，默认 60 分及格。
- **自动保存与断点续答** — 每 30 秒自动保存；刷新/中途退出后从“继续作答”进入，自动回到第一道未答题。
- **倒计时** — 默认 30 分钟（正式考试时长可由管理员配置），剩余 5 分钟红色闪烁提醒，到时自动提交。

### 成绩单与能力画像
- **能力卡片** — 展示各维度（按 `assessment_category`）题数与答对数量。
- **雷达图** — ≥3 个维度时展示各能力正确率（top8 截断），维度过少时退化为卡片。
- **AI 评估总结** — DeepSeek 基于 `skill_dimension` 聚合数据生成优缺点点评与提升建议。
- **答题详情** — 逐题列出你的作答、正确答案与【答案解析】。

### 身份与权限隔离
- 无账号体系：公开自测记录按 `visitor_id`（localStorage）隔离，公共历史仅返回本人未删除的自测记录。
- 正式考试记录归属 `candidate_session`，不出现在公共历史中，只能在后台按考试查看。
- 普通游客只能软删除**自己名下（visitor_id 匹配）的 public 自测记录**；考试记录对游客不可删。
- 管理后台 `/admin` 独立页面：登录 / Dashboard / 建考试 / 发邀请码 / 候选人列表 / 查看报告 / 删除考试（连带清理其记录）。

## 试卷结构

| 模块 | 题数 | 说明 |
|---|---|---|
| 通用基础 | 4 | 计算机网络 / 数据结构 / 编程基础 / 操作系统（必答） |
| 专业方向 | 14 | 从所选方向按比例抽取；方向可多选 1~3 个 |
| 安全常识 | 2 | 必答 |
| **合计** | **20** | 主观题 2~4 道（正式考试可在后台关闭） |

> 若完全跳过方向选择，则使用通用基础题库补足题目数量。

- 题库总量 **391 道**，题型分布：单选 247 / 多选 65 / 判断 48 / 主观 31。
- 专业方向 6 个：AI Agent / 前端开发 / 后端开发 / 测试 / 运维 / 算法与数据分析。

## 技术栈

- **后端**: Python 3.12 + FastAPI + Uvicorn + SQLite（幂等迁移，兼容旧库）
- **前端**: 纯 HTML/CSS/JS 单页应用（无框架，Hash 路由）+ Chart.js 雷达图
- **AI 评判**: DeepSeek API（未配置 Key 时主观题降级为启发式评分、总结降级为规则文案）
- **部署**: Docker Compose + Nginx（HTTPS，可选）；数据卷持久化 SQLite

## 快速开始

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置（可选）——不配 Key 则主观题不做 AI 评判
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 3. 启动
python main.py

# 4. 浏览器访问
# http://localhost:8000
```

### Docker 部署

```bash
# 复制配置、构建并启动
cp .env.example .env
docker compose up -d --build
# 服务默认暴露 8000 端口；如需公网 HTTPS，按 deploy/nginx.conf 配置反代与证书
```

## 使用流程

### 个人自测
1. 打开首页 → 点击「下一步：选择题库方向」。
2. 勾选 1~3 个专业方向（也可跳过，走通用基础题库）。
3. 答题 → 提交（或到时自动提交）→ 查看成绩单、雷达图、AI 总结与逐题解析。
4. 历史记录：仅显示当前浏览器（visitor_id）本人的自测记录，支持删除自己的记录。

### 组织化考试（管理员）
1. 访问 `/admin` → 使用管理员账号登录。
2. 「新建考试」填写名称、选择专业方向、配置时长 / 是否主观题 / 是否 AI 评分 → 生成 6 位邀请码。
3. 将邀请链接 `https://你的域名/exam/join?code=XXX`（或直接发邀请码）分发给候选人。
4. 候选人在入口页输入邀请码 + 姓名 → 确认考试信息 → 开始作答（仅一次机会）。
5. 后台「考试列表 → 候选人」查看每位候选人的进度与成绩报告；报告可通过 `/#r/<记录id>` 分享给候选人复核。

## 项目结构

```
kaohe/
├── main.py                       # 入口，启动 Uvicorn
├── question_bank.json            # 题库（391 题）与组卷配置
├── index.html                    # 考生端 SPA 入口
├── script.js                     # 考生端全部逻辑
├── style.css                     # 暗色主题样式
├── admin.html / admin.js         # 管理后台（/admin）
├── requirements.txt              # Python 依赖
├── .env.example                  # 配置模板
├── Dockerfile                    # 后端镜像（非 root 运行）
├── docker-compose.yml            # app + nginx 编排，数据卷 ./data
├── .gitignore
├── deploy/
│   └── nginx.conf                # HTTPS 反代配置模板
└── app/
    ├── main.py                   # FastAPI 应用创建（/admin、/exam/join 兜底）
    ├── config.py                 # 环境变量 / 路径 / 管理员配置
    ├── models.py                 # Pydantic 请求模型
    ├── db.py                     # SQLite 表结构与幂等迁移
    ├── api/
    │   ├── exam.py               # 加入考试 / 开始 / 续答 / 保存 / 提交
    │   ├── records.py            # 历史记录查询与软删除
    │   └── admin.py              # 管理后台登录与考试管理
    └── services/
        ├── question_service.py   # 组卷算法（比例分配/子方向权重/主观题数量控制）
        ├── exam_service.py       # 考试 CRUD / Dashboard / CandidateSession
        ├── record_service.py     # 记录管理（visitor_id 隔离、单次作答守卫、软删除）
        └── grading_service.py    # 评分引擎 + DeepSeek 批改 + AI 能力总结
```

## 题库格式

`question_bank.json` 结构：`exam_config`（组卷配置）+ `specialties`（方向列表）+ `questions`（题目数组）。

```json
{
  "exam_config": {
    "question_allocation": { "通用基础": 4, "专业方向": 14, "安全常识": 2 },
    "pass_score": 60, "full_score": 100, "time_limit_minutes": 30,
    "difficulty_weights": { "简单": 1.0, "中等": 1.5, "困难": 2.0 },
    "assessment_ratios": { "前端开发": { "HTML/CSS": 27, "JavaScript基础": 36, ... } }
  },
  "specialties": { "Agent岗位": { "label": "AI Agent", "icon": "🤖", "desc": "..." }, ... },
  "questions": [
    {
      "id": 2001,
      "module": "前端开发",            // 通用基础 | 前端开发 | 后端开发 | 测试 | 运维 | 算法数据 | Agent岗位 | 安全常识
      "category": "HTML/CSS",          // 二级分类
      "assessment_category": "HTML/CSS",  // 能力画像口径（雷达图/能力卡片），建议 = 可考核的最小维度
      "skill_dimension": ["前端基础能力"], // 供 AI 总结使用，可多标签
      "type": "single_choice | multi_choice | true_false | subjective",
      "difficulty": "简单 | 中等 | 困难",
      "weight": 1.0 | 1.5 | 2.0,
      "question": "题目文本",
      "options": ["选项A", "选项B", "..."],   // 单选/多选必填
      "answer": "正确选项文本 | [\"正确A\", \"正确B\"]",
      "explanation": "答案解析"
    }
  ]
}
```

**注意事项**：
- 多选题答案用**数组格式** `["A","B"]`；主观题不填 `options`；判断题答案为 `正确` 或 `错误` 文本。
- 新增模块若需要**按能力维度控制出题比例**，在 `exam_config.assessment_ratios.<模块>` 下配置各 `assessment_category` 的权重（整型即可，自动按比例换算）。
- 修改题库后重启服务生效。

## 配置文件 (.env)

```
# DeepSeek（AI 主观题评判 / 评估总结）
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/chat/completions
DEEPSEEK_MODEL=deepseek-chat

# 运行端口（本地直接 python 启动时）
APP_PORT=8000

# SQLite 落盘路径（Docker 下默认 /app/data/exam_records.sqlite3）
DB_PATH=exam_records.sqlite3

# 管理后台（用户名/密码 + 管理令牌）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=你的后台登录密码
ADMIN_TOKEN=你的管理令牌（历史删除 / 后台接口鉴权）
```

> 管理后台登录成功即返回该令牌；所有 `/api/admin/*` 及带权删除接口均需携带请求头 `X-Admin-Token`。

## 数据与隔离说明

- 表 `exam_records`：`mode`(public/exam)、`visitor_id`、`candidate_session_id`、`deleted` 软删除标记。
- 表 `exams`：含 `invite_code`；删除考试会**连带物理清理**其候选人记录。
- 表 `candidate_session`：`(exam_id, candidate_name)` 唯一，支撑“单次作答”与中途续答。
- 公共历史接口 `GET /api/records?visitor_id=` 只返回该游客自己的 public 记录；未带 `visitor_id` 返回空。
- 前端静态资源均带 `?v=N` 版本号（如 `/script.js?v=16`），改动前端后需同步递增 `index.html` 中的版本号并清缓存验证。

## 已知限制

- 主观题分数由 AI 依据答案完整度评判，通常不会轻易给满分，结果存在一定波动。
- AI 功能依赖 DeepSeek API 余额；未配置 Key 时自动降级为启发式评分与规则文案。
- 无注册/登录体系，身份隔离仅依赖 `visitor_id` + `CandidateSession` 两层，适合轻量测评场景。

## 项目背景与迭代过程

从本地考试 Demo 演进为公网可用的双模式评估平台，主要历程：

- **V0 本地考试 Demo**：克隆 intern-exam（dev 分支），FastAPI + SQLite + 纯前端 SPA，修复 python-dotenv 依赖后本地跑通。
- **V1 公网部署**：改造为 Docker Compose + Nginx，部署到香港服务器（43.128.23.90，域名 tingyu0721.top），Let's Encrypt 免费 HTTPS + 自动续期。
- **V2 AI 评分 + 能力画像**：DeepSeek 批改主观题（Prompt 含题目/答案要点/解析），Chart.js 雷达图 + AI 评估总结，展示口径统一到 `assessment_category`。
- **V3 题库结构化 + 智能组卷**：为全部题目补齐 `assessment_category` / `skill_dimension` 打标，`exam_config.assessment_ratios` 实现子方向按比例组卷（Agent 用规范推荐比例，其余按池子构成，均为可改配置）。
- **V4 后台管理**：`admin.html` 独立管理页（登录/Dashboard/建考试/邀请码/候选人列表/查看报告），考试流程复用组卷-答题-评分-报告链路，时长/主观题/AI 开关作用于考试。
- **V5 考试 Session 与权限隔离**：邀请码 + 姓名进入正式考试，`CandidateSession` 归档；访客 `visitor_id` 隔离自测历史；软删除与归属校验；单次作答。产品从“入职考试工具”演进为**个人自测 + 组织化招聘的双模式能力评估平台**。
