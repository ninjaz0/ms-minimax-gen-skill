# 从空实例部署

## 1. 选中正确的机器

从[魔搭我的 Notebook](https://www.modelscope.cn/my/mynotebook)打开已运行的 AMD GPU 实例，进入 Code Editor → 终端。已有实例可直接使用。若需要创建实例或更换计费规格，先确定用户选定的资源。工作区上方可查看运行状态和本次剩余时长。实际配额、闲置回收时间和磁盘容量以当前账号页面为准。

在**实例**里执行：

```bash
pwd
findmnt -T /mnt/workspace
findmnt -T /opt
df -h /opt /mnt/workspace
free -h
command -v python rocm-smi ffprobe
python - <<'PY'
import sys, torch
print(sys.executable, sys.version, torch.__version__, torch.version.hip)
print("devices", torch.cuda.device_count())
for i in range(torch.cuda.device_count()):
    p = torch.cuda.get_device_properties(i)
    print(i, p.name, round(p.total_memory / 2**30, 1), "GiB")
PY
python -c 'from modelscope.hub.file_download import model_file_download'
```

已跑通的镜像组合为 Ubuntu 22.04、Python 3.12、PyTorch 2.12.0 ROCm 版、HIP 7.2、gfx942，单卡约 191.7 GiB 可用规格、主存 200 GiB。ROCm 下 PyTorch 仍使用 `torch.cuda` API。以 PyTorch 可见设备数判断实际分配，`/dev/dri` 可能列出同宿主机多张卡。这些是实测规格，较小显存机型需要另做适配和生成验收。

若有多个 Python，选择同时能导入镜像提供的 ROCm torch 和 ModelScope SDK 的解释器，设置 `H3_PYTHON` 为其绝对路径。原实例有多个 Python 版本，单看编辑器的默认选择很容易选错。

## 2. 规划持久盘与临时盘

| 位置 | 内容 | 重建后处理 |
| --- | --- | --- |
| `/mnt/workspace/ms-minimax-gen-skill` | 此仓库、Notebook、清单和 API 图 | 保存在平台持久盘 |
| `state/ComfyUI` | 固定提交的官方源码 | 保留并核对提交 |
| `state/inputs`、`state/references`、`state/outputs`、`state/jobs` | 服务输入、Notebook 上传、MP4、任务记录与抽帧 | 可继续下载与复核 |
| `/opt/ms-minimax-h3` | 六个模型文件的缓存、venv、模型搜索路径配置 | 临时盘回收后按需要重建 |

原实例的持久目录由网络文件系统提供，`df` 显示的共享后端容量大于账号可用配额。以平台配额决定能否持久存放文件。实测采用临时盘存权重。若平台分配不同临时盘，可在终端 `export H3_CACHE=/可写临时盘/ms-minimax-h3`，然后执行后续命令。

| 模式 | 组成 | 下载量（十进制 GB） |
| --- | --- | ---: |
| T2V | FL2VA pruned BF16、文本编码器、视频 VAE、音频 VAE | 97.55 |
| R2V | Ref2VA pruned BF16、相同编码器与两个 VAE、Turbo LoRA | 99.50 |
| both | 两个主模型、编码器、两个 VAE、R2V LoRA；共享组件只存一份 | 139.73 |

R2V 标准模式使用 20 步，4 步预览才会加载 Turbo LoRA。公开脚本在部署 R2V 时同时下载 LoRA，便于直接切换。不同官方模板还有量化选项，本手册复现的是已验证的 AMD BF16 路线。新下载要为 SDK 暂存和虚拟环境预留空间，脚本在缺失文件总量之外再留一个最大缺失文件及 8 GiB。

## 3. 获取源码和依赖

```bash
cd /mnt/workspace
git clone https://github.com/ninjaz0/ms-minimax-gen-skill.git
cd ms-minimax-gen-skill
python scripts/models.py both --action plan
bash scripts/restore.sh both
```

如果需要后台运行，从仓库根目录启动一次：

```bash
mkdir -p state/logs
nohup bash scripts/restore.sh both > state/logs/restore.log 2>&1 < /dev/null &
tail -f state/logs/restore.log
```

前台与后台任选一种。原任务已运行时，检查日志和进程。恢复锁用于串行化同一缓存的安装操作。

这个命令依次做以下事情：

1. 验证 Linux、Python 3.12 和 ROCm GPU。新建独立 `state/ComfyUI`，从官方仓库取 `651ca296a73cd21c12a57eb8741d52e40dc6528f`，对应 ComfyUI 0.38.0。已有源码提交或受版本管理的文件不匹配时会停止。
2. 在临时盘创建 `--system-site-packages` 虚拟环境，继承镜像 torch。将镜像 torch 系列现有版本写入 pip 约束，再安装前端、视频解码和 Notebook 依赖。前端 1.53.10、comfy-kitchen 0.2.36、comfy-aimdo 0.5.5 与固定源码配套。
3. 注册 `ms-minimax-h3` 内核，显示名为 `MiniMax H3 (AMD)`。
4. 使用镜像中的 ModelScope SDK，从 `Comfy-Org/MiniMax-H3` 按清单的**逐文件 revision** 下载模型。每个文件落盘后检查字节数和 SHA-256，复用时也会核对摘要。[权重清单](../assets/models.lock.json)
5. 写入 ComfyUI 的额外模型搜索路径，使用 PyTorch attention，关闭 xFormers 和自定义节点，监听 `127.0.0.1:8188`。服务日志位于 `state/logs/comfy.log`。启动后检查源码版本、启动参数、所需 H3 节点。

实例访问 GitHub 受限时，可从可信机器上传此技能的源代码。ComfyUI 可先从官方仓库获取固定提交，使用 `git bundle` 搬运完整 Git 对象，在 `state/ComfyUI` 恢复同一提交再运行脚本。仅有一个解压后的源码目录不足以通过提交校验。

## 4. 从终端完成两条路径

```bash
H3_PY=/opt/ms-minimax-h3/venv/bin/python
"$H3_PY" scripts/generate.py t2v --size 480p --seconds 5 --steps 20 \
  --prompt '一只橘猫坐在窗台上，慢慢转头看向落叶。阳光温暖，镜头缓慢推进。声音是微风与鸟鸣。'
```

命令打印任务目录、`prompt_id` 和最终 JSON。以 `first_frame` 返回的实际路径作为下面的第一张参考图。用其他图片时，先通过魔搭文件树上传到实例，再把实例上的路径传给 CLI。

```bash
"$H3_PY" scripts/generate.py r2v --size 480p --seconds 5 --steps 20 \
  --image 'state/jobs/替换为上一次的任务目录名/first-frame.png' \
  --prompt '保持 <Picture 1> 中橘猫的条纹、体型和窗台场景。它转向镜头、眨眼并抬起前爪。远处有鸟鸣。'
```

每增加一张图，就再传一个 `--image`，顺序对应 `<Picture 1>` 至 `<Picture 9>`。真实 R2V 使用 `MiniMaxH3ReferenceToVideo` 与 Ref2VA 权重。上传后采用接口返回的文件名，连接 `ref_images.ref_image_0` 等输入；同时连上视频和音频 VAE。生成画面可改变视角，参考图的主体或风格约束由提示词表达。

T2V 使用 `MiniMaxH3ImageToVideo` 的纯文本路径，保留其图像输入为空。两图共用 `res_multistep`、`simple` 调度、联合音视频采样、两个解码器和 `CreateVideo` / `SaveVideo`。参考图快速预览可追加 `--turbo`，默认 4 步。[官方节点说明](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)

## 5. 在浏览器交付

在文件树内依次打开 `notebooks/t2v.ipynb` 和 `notebooks/r2v.ipynb`。选 `MiniMax H3 (AMD)` 或明确指向临时盘 `venv/bin/python` 的选项，点“全部运行”。R2V 选择图片后输入含编号的描述，再点“生成视频”。脚本在实例内访问回环地址，浏览器通过已登录的 Notebook 显示结果。

`H3_PORT` 可更改服务端口。若使用自定义端口，在启动终端导出该变量，并在 Notebook 首个代码单元调用 `show` 前设置 `os.environ["H3_PORT"]`。自定义安装目录可通过 `os.environ["H3_REPO"]` 告知 Notebook。最后分别记录命令行、内核初始化、网页提交和播放的实测情况。
