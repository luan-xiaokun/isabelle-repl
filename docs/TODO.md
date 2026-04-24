# TODO

## 2026/04/21

- [x] 形成 drawio 节点/边，以及 PRD 条目到代码模块，及对应 test case 的映射文档
- [x] 明确 acceptance gate
- [x] 补充状态机语义契约文档，说明 active/awaiting_review/stopped/completed 的触发条件与不变量
- [x] 形成 v1.5 PRD（增量 localizer + 强 snapshot + 统一 candidate source + completed/finished 双终态）
- 研究同进程 pending state 与跨进程从 records 回放恢复的区别
- 考虑 policy 当中的学习 / LLM 层机制
- 考虑扩展至 session-level proof repair campaign 的设计


(* repair (premise mutation? filter changed premises) vs general premise selection *) 
(* REPL → free variables; as prompt/skill *)
