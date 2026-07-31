# 入职考核系统

面向 Agent 实习生的入职能力测评工具，通过多模块题库 + AI 主观题评判，快速检验候选人是否具备胜任工作的基本能力。

## 功能概览

- **多方向自选** — 可选择 1~3 个专业方向（Agent/前端/后端/测试/运维/算法），系统按比例从对应题库抽题
- **智能组卷** — 通用基础 4 题 + 专业方向 14 题 + 安全常识 2 题，共 20 题；Agent 方向自动 +1 题
- **客观题即时判定** — 单选、多选、判断由后端直接比对答案
- **多选题部分给分** — 全对满分，半对（有正确但无错误）50%，错选 0 分
- **AI 批改主观题** — 接入 DeepSeek API，对简答题进行语义评判并给出评语
- **难度加权计分** — 简单 ×1.0 / 中等 ×1.5 / 困难 ×2.0
- **自动保存与断点续答** — 每 30 秒自动保存，退出/刷新后可恢复，自动跳转到第一个未答题
- **题号导航** — 颜色区分未答（灰）/ 已答（绿）/ 当前（紫），点击跳转
- **倒计时** — 30 分钟限时，剩余 5 分钟红色闪烁提醒
- **分类统计** — 考试结束后展示总分、是否通过、各模块正确率、每题详情及答案解析

## 试卷结构

| 模块 | 题数 | 说明 |
|---|---|---|
| 通用基础 | 4 | 计算机网络 / 数据结构 / 编程基础 / 操作系统 |
| 专业方向 | 14 | 从自选方向按比例抽取（Agent 方向轻微加权） |
| 安全常识 | 2 | 必答 |
| **合计** | **20** | 其中简答题 2~4 道 |

题库总量约 **390+ 道**，涵盖 8 个模块。

## 技术栈

- **后端**: Python + FastAPI + Uvicorn + SQLite
- **前端**: 纯 HTML/CSS/JS（SPA 单页应用，无框架，Hash 路由）
- **AI 评判**: DeepSeek API（可选，未配置时跳过主观题 AI 评分）

## 快速开始

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key（可选，不配置则主观题不进行 AI 评分）
cp .env.example .env
# 编辑 .env，填入你的 DEEPSEEK_API_KEY

# 3. 启动
python main.py

# 4. 浏览器访问
# http://localhost:8000
```

### 远程面试使用（ngrok 内网穿透）

让候选人通过公网链接在线答题，无需服务器和域名：

```bash
# 1. 下载 ngrok：https://ngrok.com/download
#    解压到 C:\Users\<用户名>\ngrok\

# 2. 注册 ngrok 账号，获取 authtoken
#    https://dashboard.ngrok.com/get-started/your-authtoken

# 3. 配置 Token（仅首次）
cd C:\Users\<用户名>\ngrok
ngrok.exe config add-authtoken <你的authtoken>

# 4. 启动服务 + 穿透（需要两个终端）
# 终端 1：启动考核服务
cd 项目目录
python main.py

# 终端 2：启动 ngrok
cd C:\Users\<用户名>\ngrok
ngrok.exe http 8000

# 5. 将显示的 https://xxxx.ngrok-free.dev 链接发给候选人
# 面试结束 Ctrl+C 关闭两个终端即可
```

> **注意**：免费版 ngrok 每次重启链接地址会变化，面试前现开即可。每月 1GB 带宽，日常使用完全够用。

## 项目结构

```
kaohe/
├── main.py                       # 入口，启动 Uvicorn
├── question_bank.json            # 题库（390+ 题）
├── exam_records.sqlite3          # 考试记录数据库（gitignore）
├── index.html                    # SPA 单页入口
├── script.js                     # 前端全部逻辑
├── style.css                     # 暗色主题样式
├── requirements.txt              # Python 依赖
├── .env                          # 本地密钥（不提交）
├── .env.example                  # 配置模板
├── .gitignore
└── app/
    ├── main.py                   # FastAPI 应用创建
    ├── config.py                 # 环境变量 / 路径配置
    ├── models.py                 # Pydantic 请求/响应模型
    ├── db.py                     # SQLite 数据库操作
    ├── api/
    │   ├── exam.py               # 组卷 / 提交 / 保存进度接口
    │   └── records.py            # 历史记录查询接口
    └── services/
        ├── question_service.py   # 组卷算法（分配/加权/主观题控制）
        ├── grading_service.py    # 评分引擎（部分给分/难度加权/AI评判）
        └── record_service.py     # 考试记录管理
```

## 题库格式

在 `question_bank.json` 中按以下格式增删题目：

```json
{
  "id": 唯一编号,
  "module": "通用基础 | 前端开发 | 后端开发 | 测试 | 运维 | 算法数据 | Agent岗位 | 安全常识",
  "category": "二级分类（如 JavaScript / Docker / 测试基础 等）",
  "type": "single_choice | multi_choice | true_false | subjective",
  "difficulty": "简单 | 中等 | 困难",
  "weight": 1.0 | 1.5 | 2.0,
  "question": "题目文本",
  "options": ["选项A", "选项B", ...],
  "answer": "正确选项文本 | [\"正确A\", \"正确B\"]",
  "explanation": "答案解析"
}
```

**注意事项**：
- 多选题答案使用 **数组格式** `["A", "B"]`，不要使用 `"A|B"` 字符串
- 主观题不需要 `options` 字段
- 修改题库后重启服务生效
- `exam_config` 中可调整各模块抽题数量、及格线、倒计时等参数

## 配置文件 (.env)

```
DEEPSEEK_API_KEY=sk-xxxx          # DeepSeek API 密钥（可选）
DEEPSEEK_MODEL=deepseek-chat      # 模型名称
APP_PORT=8000                     # 服务端口
```

## 答题流程

1. 首页 → 查看考试说明（20 题 / 30 分钟 / 60 分及格）
2. 选择专业方向（1~3 个，也可跳过使用通用基础）
3. 答题：单选/多选点击选项，判断选对错，主观题输入文字
4. 题号导航条可随时跳转，进度每 30 秒自动保存
5. 提交 → 展示总分、通过状态、分类统计、逐题解析

## 已知限制

- ngrok 免费版每次重启链接变化，需面试前重新分发
- ngrok 访问时对方会先看到 ngrok 确认提示页（点一下即进入）
- AI 主观题评分依赖 DeepSeek API 余额
- 仅支持单人单次考试，无并发考生管理
