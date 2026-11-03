# ms-minimax-gen-skill

在魔搭社区的 DSW-AMD Notebook 实例上部署 MiniMax H3，生成带立体声音轨的 MP4。仓库提供文生视频（T2V）和参考图生视频（R2V）的原生 ComfyUI API 图、中文 Notebook、权重清单和恢复脚本。推理在实例内完成，无需 MiniMax API Key。

**给 Agent 使用**：从 [SKILL.md](SKILL.md) 开始。支持目录式技能的客户端可将整个仓库克隆到自己的 skills 目录，文件夹名使用 `ms-minimax-gen-skill`。也可以把该入口链接交给能操作远程终端的 Agent。

**在实例终端运行**（先确认所选 AMD 镜像、剩余时长和临时盘容量）：

```bash
cd /mnt/workspace
git clone https://github.com/ninjaz0/ms-minimax-gen-skill.git
cd ms-minimax-gen-skill
python scripts/models.py both --action plan
bash scripts/restore.sh both
/opt/ms-minimax-h3/venv/bin/python scripts/generate.py t2v \
  --prompt '窗台上的橘猫转头看向飘落的银杏叶。镜头缓慢推进，背景有轻风和鸟鸣。'
```

打开 `notebooks/t2v.ipynb` 或 `notebooks/r2v.ipynb`，选择 `MiniMax H3 (AMD)` 内核后点“全部运行”。R2V 支持按顺序上传 1–9 张参考图，在提示词中用 `<Picture 1>`、`<Picture 2>` 指定各图的作用。

| 任务 | 文档 |
| --- | --- |
| 选实例、核对环境、首次部署、下载与运行两套工作流 | [部署手册](references/deployment.md) |
| 判断是否跑通、测首轮时间、核查缓存与音视频 | [验收方法与实测记录](references/validation.md) |
| 实例重建、复用已有部署、处理网页空白或安全清理空间 | [恢复与故障排查](references/recovery.md) |
| 对照每个文件的版本、大小与 SHA-256 | [权重清单](assets/models.lock.json) |

**验证范围**。原部署在 192 GB 显存的 AMD 实例上完成过冷启动和重建恢复。两套工作流均实际生成了 864×480、124 帧、约 5.17 秒的视频，T2V 还验证过 1344×768。仓库中的固定节点和权重取自这套实测配置。首次克隆、路径布局和启动工具是为公开复现整理的，验证记录区分了原实例 GPU 实测和公开脚本的离线检查。

模型按需从 Comfy-Org 的魔搭仓库下载。模型的使用条款见[模型卡](https://huggingface.co/Comfy-Org/MiniMax-H3)和[MiniMax 官方发布](https://github.com/MiniMax-AI/MiniMax-H3)。
