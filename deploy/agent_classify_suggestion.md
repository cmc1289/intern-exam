# Agent 岗位 80 题分类建议表（V1.0 规范）

> 供人工审核。分类名采用规范全名：
> Agent基础 | RAG知识增强 | Prompt工程 | Agent架构与框架 | Tool Calling与MCP | Memory与上下文管理 | Agent安全 | Agent工程实践
>
> 规范目标分布：Agent基础12 / RAG16 / Prompt12 / 架构与框架12 / Tool-Calling与MCP12 / Memory4 / 安全8 / 工程实践4

| 题号 | 建议分类 | 理由 | 备注 |
|---|---|---|---|
| 7001 | Agent基础 | Agent 与普通 LLM 调用的本质区别，核心概念 |  |
| 7002 | Agent基础 | Agent 核心组件构成，概念层 |  |
| 7003 | Agent基础 | ReAct 范式含义 |  |
| 7010 | RAG知识增强 | RAG 解决大模型知识时效/幻觉问题 |  |
| 7011 | Memory与上下文管理 | 记忆模块分类（短期/长期） |  |
| 7012 | Tool Calling与MCP | Function Calling 与 MCP 关系 |  |
| 7013 | Agent架构与框架 | Single vs Multi-Agent 架构选型 |  |
| 7014 | Prompt工程 | CoT 引导「让我们一步步思考」属提示设计 |  |
| 7015 | RAG知识增强 | RAG 检索优化策略（重排/多路召回等） |  |
| 7022 | Agent基础 | Agent Loop 步骤顺序，属工作流程 |  |
| 7023 | Agent基础 | Reflexion 与 ReAct 范式差异 | 偏 Memory（自我反思入长期记忆） |
| 7024 | Agent基础 | 防死循环策略，Agent Loop 健壮性设计 |  |
| 7025 | Tool Calling与MCP | MCP Server 端职责 |  |
| 7026 | Agent架构与框架 | A2A 协议：Agent 间协作问题 |  |
| 7027 | Agent架构与框架 | A2A Agent Card 作用（Agent 间发现） |  |
| 7029 | Agent基础 | Agent 与直接调 LLM API 的本质区别 |  |
| 7030 | Agent架构与框架 | 多 Agent 编排模式（流水线/辩论/并行） |  |
| 7033 | Tool Calling与MCP | FC 与 MCP 定位差异 |  |
| 8048 | Agent基础 | Agent「幻觉」概念定义 |  |
| 8050 | Agent架构与框架 | Multi-Agent 通信方式辨析 |  |
| 8051 | Tool Calling与MCP | Tool Calling 是否支持动态扩展 |  |
| 8100 | Agent基础 | Agent 与 LLM 系统关系，核心概念 |  |
| 8101 | Agent基础 | 标准 Agent Loop 核心步骤 |  |
| 8102 | Agent基础 | ReAct 中 Thought/Action/Observation 交替机制 |  |
| 8103 | Agent基础 | Plan-and-Execute 范式概念 |  |
| 8104 | Tool Calling与MCP | Function Calling 核心工作流 |  |
| 8105 | Tool Calling与MCP | MCP 架构 Client-Server |  |
| 8106 | Tool Calling与MCP | MCP 传输方式（stdio/HTTP+SSE） |  |
| 8107 | Tool Calling与MCP | MCP 与 Function Calling 区别辨析 |  |
| 8108 | Agent架构与框架 | A2A Agent Card 自描述元数据 |  |
| 8109 | Agent架构与框架 | A2A 与 MCP 协议层次关系 |  |
| 8110 | Agent架构与框架 | Sequential 顺序编排模式 |  |
| 8111 | Agent架构与框架 | Debate 辩论模式思想 |  |
| 8112 | Memory与上下文管理 | 短期记忆 vs 长期记忆定义 |  |
| 8113 | Memory与上下文管理 | 上下文压缩丢信息风险 |  |
| 8115 | Agent基础 | Reflexion 核心思想（执行后反思范式） | 偏 Memory：反思写入长期记忆 |
| 8116 | RAG知识增强 | RAG 在 Agent 系统中的集成应用 |  |
| 8117 | Agent安全 | Agent 系统安全威胁辨析 |  |
| 8118 | Agent基础 | 防死循环/终止控制措施（Max Steps+预算） |  |
| 8119 | Agent工程实践 | 生产部署成本控制 |  |
| 8120 | Tool Calling与MCP | Skill 与 MCP Tool 抽象层次关系 |  |
| 8121 | Agent工程实践 | Agent 评估（Evaluation）多维指标 |  |
| 8122 | Memory与上下文管理 | 工作记忆（Working Memory）概念 |  |
| 8123 | Agent架构与框架 | Hierarchical 分层编排模式 |  |
| 8124 | Tool Calling与MCP | 工具 JSON Schema 关键字段 |  |
| 8125 | Agent基础 | Agent 核心组件多选，概念层 |  |
| 8126 | Tool Calling与MCP | MCP Server 可暴露能力（Tools/Resources/Prompts） |  |
| 8127 | Agent基础 | ReAct 相比纯 CoT 的优势 |  |
| 8129 | Memory与上下文管理 | 上下文压缩策略 |  |
| 8131 | Agent基础 | Plan-and-Execute 适用场景选择 |  |
| 8132 | Memory与上下文管理 | 长期记忆实现方案（向量库/知识图谱） |  |
| 8134 | Tool Calling与MCP | MCP 核心设计原则 |  |
| 8135 | Tool Calling与MCP | MCP 传输是否必须 HTTPS |  |
| 8136 | Agent基础 | ReAct 中 Thought/Action 是否严格分离 |  |
| 8137 | Tool Calling与MCP | MCP Server 多 Client 并发 |  |
| 8138 | Agent基础 | Agent 终止条件判定（可多方式） |  |
| 8139 | Agent架构与框架 | A2A Agent Card 是否可变更 |  |
| 8140 | Agent基础 | 主观题：Reflexion 工作流程及与出错重试区别 | 偏 Memory |
| 8144 | Tool Calling与MCP | 主观题：MCP 三原语 Tools/Resources/Prompts 区别 |  |
| 8145 | Agent架构与框架 | 主观题：Agent Card 字段 + 发现/任务委派流程 |  |
| 8150 | Agent基础 | Token 基础概念（LLM 底层知识） |  |
| 8151 | Memory与上下文管理 | Context Window 上下文窗口概念 |  |
| 8152 | Agent基础 | Temperature 参数作用（LLM 生成基础） |  |
| 8153 | Agent基础 | 大模型训练 vs 推理（LLM 基础） |  |
| 8154 | Prompt工程 | Prompt 是沟通方式，提示工程基础 |  |
| 8155 | RAG知识增强 | RAG 是什么 |  |
| 8156 | RAG知识增强 | RAG 解决的私有知识/幻觉问题 |  |
| 8157 | RAG知识增强 | Embedding 在 RAG 中的作用 |  |
| 8158 | RAG知识增强 | Chunking 分块目的 |  |
| 8159 | RAG知识增强 | Reranking 重排序作用 |  |
| 8160 | RAG知识增强 | RAG 核心流程（摄取-分块-向量化-检索-生成） |  |
| 8161 | Agent基础 | ReAct 三元组 Thought-Action-Observation |  |
| 8162 | Agent基础 | ReAct 相对纯 CoT 优势 |  |
| 8163 | Tool Calling与MCP | 工具定义 JSON Schema 描述入参 |  |
| 8164 | Tool Calling与MCP | Function Calling 是否由模型直接执行 |  |
| 8165 | Agent基础 | Agent 循环终止条件判断 |  |
| 8166 | Agent基础 | Plan-and-Execute 与 ReAct 模式区别 |  |
| 8167 | Tool Calling与MCP | MCP 核心定位（工具接入协议） |  |
| 8168 | Tool Calling与MCP | 为何需要 MCP 而非 HTTP 直连 |  |
| 8169 | Tool Calling与MCP | MCP 两个核心角色 Client/Server |  |

## 分布统计（对比规范目标）

| 分类 | 建议数 | 规范目标 | 差异 |
|---|---|---|---|
| Agent基础 | 27 | 12 | +15 ⚠️ |
| RAG知识增强 | 9 | 16 | -7 ⚠️ |
| Prompt工程 | 2 | 12 | -10 ⚠️ |
| Agent架构与框架 | 12 | 12 | +0  |
| Tool Calling与MCP | 20 | 12 | +8 ⚠️ |
| Memory与上下文管理 | 7 | 4 | +3 ⚠️ |
| Agent安全 | 1 | 8 | -7 ⚠️ |
| Agent工程实践 | 2 | 4 | -2 ⚠️ |
| **合计** | 80 | 80 | | |