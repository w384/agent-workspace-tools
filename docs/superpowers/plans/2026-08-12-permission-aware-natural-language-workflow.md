\# 企业演示 Demo 实施计划



\## Demo 目标



验证不同 Dify 用户根据 `sys.user\_id` 获得不同本机工作区权限：



```text

Dify sys.user\_id

→ SQLite 人员权限表

→ 服务端过滤可见路径

→ create\_plan 拒绝越权操作

→ Human Input 确认

→ execute\_confirmed\_plan 再次校验

