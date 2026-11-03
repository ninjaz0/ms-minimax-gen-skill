---
name: ms-minimax-gen-skill
description: 在魔搭社区 ModelScope DSW-AMD 实例上检查、部署、恢复并验收 MiniMax H3 的本地文生视频和参考图生视频工作流。适用于 ROCm、ComfyUI 和 Jupyter Notebook 的实例操作。
---

先确定用户要检查已有实例、首次部署还是重建恢复，以及需要 T2V、R2V 或两者。**“工作流还在”要分开回答四件事**：持久盘文件、临时盘权重、运行中的服务、这次实例是否真实完成过生成。

1. 在用户指定的魔搭实例终端执行操作。确认 `pwd`、挂载点、GPU 和 Python。需要浏览器时，定位已登录的“我的 Notebook”或“代码工作区”，打开下方面板的“终端”。机器名、浏览器标签 ID、按钮编号和连接 URL 都要现场读取。
2. 首次部署读[部署手册](references/deployment.md)。先用 `scripts/models.py MODE --action plan` 计算下载量。公开版自行取固定版本的 ComfyUI，将源码和产物放在持久盘，将虚拟环境和权重放在临时盘。选择 `t2v`、`r2v` 或 `both`。已有项目先查路径和软链接，再决定是否复用。
3. 文件存在而临时盘已被回收时，读[恢复手册](references/recovery.md)。仅检查的请求先报告缺失量。部署或恢复已获授权后，执行 `bash scripts/restore.sh MODE` 并跟踪日志到完成。已有服务占用端口时核实归属，使用独立端口时让 CLI 与两个 Notebook 都指向同一端口。
4. 按[验收方法](references/validation.md)逐个运行要求的工作流。首次可用 480p、5 秒、20 步。T2V 只给文字，R2V 至少上传一张图片并明确其角色。可使用刚生成视频的第一帧验证 R2V。随机种子默认每次更新。
5. 检查 `state/jobs/<run-id>/validation.json`、MP4 完整解码、音轨和抽帧。验收推理性能时检查 `sampler_cached`。需要网页工作台时，另测选择内核、上传、生成、自动显示结果；CLI 成功与浏览器通过分别记录。

交付实例目录、实际测试模式、参数、时长、结果路径和恢复命令。未测的模式或网页环节单独标明。清理其他项目是独立操作，仅在用户要求时按[清理流程](references/recovery.md#清理无关项目)实施。
