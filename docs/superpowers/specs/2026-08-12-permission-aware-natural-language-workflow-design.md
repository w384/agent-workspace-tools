\# 权限感知的自然语言整理工作流设计



日期：2026-08-12

状态：已确认

基线：v0.0.4



\## 目标



在现有安全闭环基础上，增加自然语言生成整理计划，并按 Dify 登录用户的组织权限限制可访问路径。



流程：



Dify 用户输入整理要求

→ list\_files 返回当前页文件元数据

→ LLM 生成 operations\_json

→ create\_plan 校验并生成确认摘要

→ Human Input 人工确认

→ execute\_confirmed\_plan 执行



\## 身份与权限



\- 使用 Dify 的 sys.user\_id 作为权限匹配主键。

\- 当前 Dify Workflow 未提供邮箱系统变量。

\- email 由本机人员架构表维护，仅用于审计，不作为授权依据。

\- 未匹配人员、停用人员默认拒绝访问。



\## SQLite 权限表



数据库：



work/security/workspace-permissions.db



employees：



\- user\_id：唯一主键

\- email：审计邮箱

\- business\_unit：事业部

\- department：部门

\- position：岗位

\- enabled：是否启用



employee\_path\_prefixes：



\- user\_id

\- path\_prefix



path\_prefix 使用相对于 D:\\AI\\AgentWorkspace 的路径：



\- 空字符串：整个工作区

\- 1：D:\\AI\\AgentWorkspace\\1

\- 项目A：D:\\AI\\AgentWorkspace\\项目A



授权目录递归包含其子目录，但不会向上扩展。



\## 服务端安全边界



\- 所有读取、计划和执行接口都必须进行 user\_id 权限校验。

\- 路径只能是工作区内相对路径。

\- 拒绝绝对路径、..、越权路径和路径边界绕过。

\- create\_plan 校验一次，execute\_confirmed\_plan 执行前再次校验。

\- LLM 生成越权路径时，由服务端拒绝。

\- 权限拒绝不暴露服务器绝对路径或其他人员信息。



\## 管理方式



第一版不做管理页面，使用本机管理员脚本维护 SQLite：



service/scripts/manage\_permissions.py



支持：



\- 添加人员

\- 修改组织信息

\- 启用或停用人员

\- 添加或移除授权路径

\- 查看人员当前权限



权限数据库和密钥不提交 Git。



\## LLM 约束



LLM 只接收：



\- 用户整理要求

\- 当前页最多 10 个文件的元数据

\- 当前用户可访问的路径范围



LLM 不读取文件正文。



LLM 只输出合法 JSON 数组，操作类型仅允许：



\- create\_folder

\- move\_rename

\- trash



禁止：



\- 绝对路径

\- ..

\- 越权路径

\- 无法明确判断的文件

\- 超过 10 个文件的批次



非法 JSON、非数组或越权计划直接停止，不进入确认和执行。



\## 审计



计划和操作日志记录：



\- user\_id

\- email

\- business\_unit

\- department

\- position

\- 授权路径前缀

\- plan\_id

\- operation\_id

\- 操作类型

\- 操作结果

\- 时间



日志继续保留 14 天。



\## 非目标



本阶段暂不实现：



\- Dify 邮箱自动获取

\- 权限管理页面

\- Agent 自主执行写入

\- 绕过 Human Input 的执行

\- 公网访问

\- 永久删除文件

