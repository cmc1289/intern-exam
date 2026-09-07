# 智能技术能力评估平台

> 面向 **AI 岗位招聘与个人自测**的双模式在线技术能力评估平台：`管理员建考试 → 生成入口 → 候选人作答 → AI 评分 → 能力画像 → 结构化 PDF 报告归档` 的完整业务闭环，并内置 **AI 智能扩充题库** 的知识工程流水线。

从最初的企业智能体实习生「入职考核 Demo」演进而来，现已升级为可部署、可运营的**智能技术能力评估平台**——个人自测、组织化招聘、AI 题库生产三合一。

---

## 能力树总览

### 1. 考试业务闭环（完整产品流程）

不再只是「打开页面 → 答题 → 看分数」，而是一条面向招聘的完整链路：

```
管理员创建考试（方向/时长/主观题/AI 评分开关）
        ↓
生成考试入口（6 位邀请码，CandidateSession 身份归档）
        ↓
候选人验证（邀请码 + 姓名，同一考试仅一次作答机会）
        ↓
智能组卷（多方向按比例 / 子方向按 assessment_ratios 权重抽题）
        ↓
在线答题（自动保存 30s、断点续答、倒计时）
        ↓
AI 评分（客观题自动判分 + 主观题 DeepSeek 语义批改）
        ↓
能力分析（assessment_category 维度统计 → 能力卡片 + 雷达图）
        ↓
报告生成（AI 评估总结 / 综合评语 / 岗位匹配建议）
        ↓
PDF 归档（结构化评估报告：摘要页 / 能力画像 / 综合评析 / 答题附录）
```

### 2. AI 能力

| 能力 | 说明 |
|---|---|
| **主观题 AI 评分** | 题干 + 参考答案要点 + 答案解析 + 考生答案**四元约束**进 Prompt，语义评判并给分、给评语 |
| **能力画像** | 统计落到 `assessment_category`，渲染能力卡片 + 雷达图（≥3 维展示，top8 截断） |
| **AI 评估总结** | 基于 `skill_dimension` 聚合结果，生成优缺点点评与提升建议 |
| **AI 智能扩充题库** | 两种模式：⚡ 快速脑暴（话题直出）/ 🔗 URL 定向清洗（参考页精炼），见下 |

**URL 定向清洗出题**——一个轻量级「知识工程」流水线，而非简单"调大模型 API"：

```
外部知识源（用户提供 URL / 话题）
        ↓
内容解析（抓取单页正文，失败明确报错，不静默回退）
        ↓
候选收集（AI 提炼 15~25 条候选问题）
        ↓
AI 筛选（剔除过难 / 无关 / 冷门，保留高价值候选）
        ↓
知识抽取与聚合（聚类为知识点，映射到已有能力维度白名单，防止孤儿维度）
        ↓
重新设计题目（不抄原题，按知识点重写题干 + 选项/答案/解析/难度/双维打标）
        ↓
人工审核（dry_run 仅预览 → 确认后入库）
        ↓
入库热生效（自动 .bak 备份 → 原子写文件 → 内存热重载，无需重启）
```

### 3. 数据模型：结构化知识体系

题目不是简单 `{question, answer, category}`，而是**面向能力评估的多维结构化知识体系**（全库 435 道已统一打标）：

```json
{
  "module": "Agent岗位",
  "category": "RAG知识增强能力",
  "assessment_category": "RAG",          // 能力画像口径（卡片/雷达图，组卷比例单位）
  "skill_dimension": ["RAG知识增强能力"],  // AI 总结口径（可多标签）
  "type": "single_choice",
  "difficulty": "中等",
  "weight": 1.5,
  "question": "...", "options": ["..."], "answer": "...", "explanation": "..."
}
```

- **8 个模块**（435 题）：Agent岗位 104 / 前端 63 / 后端 59 / 算法数据 53 / 运维 51 / 测试 50 / 通用基础 35 / 安全常识 20
- **题型**：单选 267 / 多选 76 / 判断 52 / 主观 40
- **难度**：简单 142 / 中等 232 / 困难 61
- `assessment_ratios` 让组卷按能力子方向比例出题；未配置比例的轻量模块池内随机即可（其卷面占比本来就低）

### 4. 工程与部署

完整的"本地项目 → 公网服务"落地能力：

```
本地开发（FastAPI + SQLite + 纯前端 SPA）
   ↓
Docker Compose 打包（app + nginx 双容器）
   ↓
Ubuntu 云服务器（香港，43.128.23.90）
   ↓
Nginx 反向代理（域名 tingyu0721.top / www）
   ↓
Let's Encrypt 免费 HTTPS + 自动续期
   ↓
数据卷持久化（题库/数据库落盘 ./data，容器重建不丢；AI 扩充的热重载题库也在卷内）
```

### 5. 产品化功能

- **管理后台 `/admin`**：登录鉴权 → Dashboard 数据看板 → 创建考试 → 考试与候选人管理 → 查看能力报告
- **结构化 PDF 报告**：管理员一键导出，分页呈现「摘要 → 能力画像 → AI 综合分析 → 答题附录」，含报告编号 / 评分等级 / 岗位匹配 / 页眉页脚
- **题库中心**：能力覆盖健康分析（各方向分布 / 难度 / 缺口告警与建议补题量）+ AI 智能扩充
- 深链直达：`/exam/<code>` 进入考试入口、`/#r/<记录id>` 直达报告，SPA 路由同步渲染无闪烁

---

## 试卷结构

| 模块 | 题数 | 说明 |
|---|---|---|
| 通用基础 | 4 | 计算机网络 / 数据结构 / 编程基础 / 操作系统（必答） |
| 专业方向 | 14 | 从所选方向抽取（可多选 1~3 个，多方向按比例分摊） |
| 安全常识 | 2 | 必答 |
| **合计** | **20** | 主观题 2~4 道（正式考试可在后台关闭） |

## 技术栈

- **后端**：Python 3.12 · FastAPI · Uvicorn · SQLite（幂等迁移，兼容旧库与存量数据）
- **前端**：纯 HTML/CSS/JS SPA（无框架，Hash 路由）+ Chart.js 雷达图
- **AI**：DeepSeek API（主观题批改 / 评估总结 / 题库生成）——未配置 Key 时自动降级（启发式评分 + 规则文案）
- **PDF**：ReportLab（服务端向量雷达图，中文 CID 字体，无系统字体依赖）
- **部署**：Docker Compose + Nginx + Let's Encrypt

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置（可选）——不配 Key 则主观题不做 AI 评判
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 3. 启动
python main.py
# 浏览器访问 http://localhost:8000
```

Docker 部署：

```bash
cp .env.example .env
docker compose up -d --build
```

## 使用流程

### 个人自测
首页 → 选择 1~3 个专业方向 → 答题 → 提交 → 查看成绩单 / 雷达图 / AI 总结 / 逐题解析；记录按浏览器 `visitor_id` 隔离，仅本人可见、可删。

### 组织化考试（管理员）
1. `/admin` 登录（用户名 / 密码来自 `.env`，接口带 `X-Admin-Token`）。
2. 新建考试：名称 / 专业方向 / 时长 / 主观题与 AI 开关 → 生成 6 位邀请码。
3. 将邀请链接分发给候选人 → 候选人填写邀请码 + 姓名进入 → 开始作答（仅一次机会，支持中途续答）。
4. 后台查看每位候选人进度与能力报告 → 一键导出 **PDF 报告**归档。

### AI 扩充题库（管理员）
1. 「题库中心 · 能力覆盖健康分析」查看各方向题量 / 难度 / 缺口告警。
2. 「AI 智能扩充」选方向，填话题（脑暴模式）或参考 URL（URL 模式），可写明「补 N 道」硬控数量。
3. 勾选「仅预览」先审题 → 确认后正式入库（自动 .bak + 热重载，即刻可被组卷抽中）。

## API 一览

| 分组 | 接口 | 说明 |
|---|---|---|
| 考试 | `GET /specialties` | 方向列表 |
| | `POST /exams/join` | 邀请码 + 姓名加入考试 |
| | `GET /exam/start` · `GET /exam/resume/{id}` | 开始 / 续答 |
| | `POST /exam/save/{id}` · `POST /exam/submit` | 自动保存 / 提交 |
| 记录 | `GET /records?visitor_id=` · `DELETE /records/{id}` | 本人记录 / 归属校验软删除 |
| 报告 | `GET /report/{record_or_session}/pdf` | PDF 导出（管理员） |
| 管理 | `/admin/login` · `/dashboard` · `/exams*` | 登录 / 看板 / 考试管理 |
| 题库 | `/admin/bank/health` · `/catalog` · `/expand` | 健康分析 / 目录 / AI 扩充（异步任务） |

## 项目结构

```
kaohe/
├── main.py                       # 入口
├── question_bank.json            # 题库（435 题，含组卷配置 exam_config）
├── index.html / script.js        # 考生端 SPA（根路径绝对引用 + ?v=N 版本号）
├── style.css
├── admin.html / admin.js         # 管理后台
├── requirements.txt · Dockerfile · docker-compose.yml
├── deploy/
│   └── nginx.conf                # HTTPS 反代配置
└── app/
    ├── main.py                   # FastAPI 装配（/admin、/exam/{id} 深链兜底）
    ├── config.py · models.py · db.py
    ├── api/
    │   ├── exam.py               # 组卷 / 答题 / 提交 / 续答
    │   ├── records.py            # 记录查询与软删除
    │   ├── report.py             # PDF 报告导出
    │   └── admin.py              # 后台 + 题库健康 / AI 扩充
    └── services/
        ├── question_service.py   # 组卷算法 + 题库目录 / 健康统计 / 热重载
        ├── exam_service.py       # 考试 CRUD / CandidateSession
        ├── record_service.py     # 记录与身份隔离
        ├── grading_service.py    # 评分引擎 + DeepSeek 批改
        ├── pdf_service.py        # 结构化 PDF 渲染
        └── bank_expansion_service.py  # AI 扩充流水线（候选→筛选→聚合→重设计→入库）
```

## 数据与隔离（无账号体系）

- 身份仅两层：`visitor_id`（浏览器本地，隔离自测记录）+ `CandidateSession`（(exam, candidate_name) 唯一，正式考试归档）。
- 记录软删除 `deleted=1`，普通游客只能删自己名下的 public 记录；考试记录对游客不可删，管理员删考试时连带清理。
- 公共历史只返回本人 public 记录；考试记录仅后台可见。

## 已知限制

- 主观题评分由 AI 依据答案完整度评判，结果存在合理波动；正式考试可关 AI 或人工复核。
- 无注册 / 登录体系，适合轻量测评与招聘初筛场景，深度权限管理可再演进。
- URL 定向清洗目前为单页粗提取，反爬 / JS 渲染页面会抓取失败并明确报错（不会静默回退）。

---

## 项目背景与迭代过程

从「内部入职考试 Demo」演进为「可部署的智能化技术能力评估平台」，完整历程：

- **V0 本地考试 Demo**：克隆 intern-exam（dev 分支），FastAPI + SQLite + 纯前端 SPA，修复依赖后本地跑通，先作为入职考核工具。
- **V1 公网部署**：改造 Docker Compose + Nginx，部署至香港服务器（43.128.23.90），域名 tingyu0721.top（含 www），Let's Encrypt 免费 HTTPS + 自动续期。
- **V2 AI 评分 + 能力画像**：DeepSeek 批改主观题（Prompt 含题目/答案要点/解析约束）；Chart.js 雷达图 + AI 评估总结；展示口径统一到 `assessment_category`。
- **V3 题库结构化 + 智能组卷**：全量题目补齐 `assessment_category` / `skill_dimension` 打标；`exam_config.assessment_ratios` 支持子方向按比例组卷。
- **V4 后台管理**：独立 admin 页面（登录 / Dashboard / 建考试 / 邀请码 / 候选人列表 / 查看报告），时长 / 主观题 / AI 开关作用于考试。
- **V5 考试 Session 与权限隔离**：邀请码 + 姓名进入正式考试，CandidateSession 归档；visitor_id 隔离自测历史；软删除 + 归属校验；单次作答。产品演变为**个人自测 + 组织化招聘的双模式平台**。
- **V6 结构化 PDF 报告**：ReportLab 渲染分页评估报告（摘要 / 能力画像 / AI 综合分析 / 答题附录），含报告编号 `ASSESS-日期-序号`、评分等级、岗位匹配、页眉页脚；管理员一键导出归档。
- **V7 AI 题库中心（本轮）**：能力覆盖健康分析 + AI 智能扩充（脑暴 / URL 两种显式模式 + 数量硬控 + 白名单维度模糊映射防孤儿维度 + dry_run 审核 + 自动备份热重载），将题库从固定内容升级为**可持续自生产的结构化知识库**。
