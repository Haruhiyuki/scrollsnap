# scrollsnap-core

面向 GUI agent 的滚动录屏重建工具库，用尽量少的图像证据支撑模型判断。

语言：[English](README.md) | [简体中文](README.zh-CN.md)

## 摘要

`scrollsnap-core` 会把一段垂直滚动录屏整理成紧凑、可查询的轨迹文件
（trace）：滚动视口、页面/场景边界、每一帧在长页面坐标中的位置、
可选长图拼接、局部分块图，以及每个原始帧裁剪的来源关系。

这个项目不是给终端用户使用的截图软件，而是给 agent 管线调用的工程库。
它的核心目标很明确：如果一份小型 trace 加少量精确裁剪已经足够，就不再把大量重复滚动视频帧发送给视觉模型。

当前版本以 Python 为主，算法确定性强，并围绕稳定的 `trace.json` 契约构建。
它提供 CLI、Python API、OpenClaw 风格适配器、外部视觉解析器适配器，以及一个轻量的 stdio MCP 风格服务。

## 安装

从 PyPI 安装：

```bash
pip install scrollsnap-core
```

本地源码安装：

```bash
python3 -m pip install -e ".[dev]"
scrollsnap --help
```

如需运行浏览器场景：

```bash
python3 -m pip install -e ".[browser]"
python3 -m playwright install chromium
```

核心实现依赖 Python/OpenCV/Pillow。本版本没有发布 npm wrapper，因为一个暗中依赖系统 Python 环境的薄 Node 包并不适合生产管线。

## 快速开始

只生成 trace，供模型管线按需取图：

```bash
scrollsnap analyze recording.mp4 --out run/scrollsnap --stream --no-images
scrollsnap compact-trace run/scrollsnap/trace.json
scrollsnap query-crop run/scrollsnap/trace.json \
  --segment 0 --bbox 0,1200,760,640 --video recording.mp4 --out run/crops
scrollsnap estimate-tokens run/scrollsnap/trace.json
```

同时输出长图和分块图：

```bash
scrollsnap analyze recording.mp4 --out run/full
```

验证命令：

```bash
scrollsnap selftest --out artifacts/selftest --frames 96
scrollsnap benchmark --frames 160 --repeats 3
scrollsnap release-report --out reports/release
```

## Python API

```python
from scrollsnap import analyze_scroll_recording, query_scroll_crop

analysis = analyze_scroll_recording(
    "recording.mp4",
    "run/scrollsnap",
    stream=True,
    images=False,
)

crops = query_scroll_crop(
    analysis["trace_path"],
    segment_index=0,
    bbox=(0, 1200, 760, 640),
    video_path="recording.mp4",
    out_dir="run/crops",
    limit=2,
)
```

`trace` 查询辅助函数：

```python
from scrollsnap.trace import load_trace, tiles_for_bbox, frames_for_y_range, frame_crops_for_bbox

trace = load_trace("run/scrollsnap/trace.json")
tiles = tiles_for_bbox(trace, segment_index=0, bbox=(0, 1200, 760, 640))
frames = frames_for_y_range(trace, segment_index=0, y=1200, height=640)
source_crops = frame_crops_for_bbox(trace, segment_index=0, bbox=(0, 1200, 760, 640), limit=2)
```

## Agent 集成

OpenClaw 风格工具：

```bash
scrollsnap openclaw-manifest
scrollsnap openclaw-analyze recording.mp4 --out run/scrollsnap
scrollsnap openclaw-query run/scrollsnap/trace.json \
  --segment 0 --bbox 0,1200,760,640 --video recording.mp4 --out run/crops
```

外部视觉解析器：

```bash
scrollsnap parse-region run/scrollsnap/trace.json \
  --video recording.mp4 \
  --out run/parsed \
  --segment 0 \
  --bbox 0,1200,760,640 \
  --vision-command "python3 my_parser.py --image {image} --context {context_json}"
```

MCP 风格 stdio 服务：

```bash
scrollsnap-mcp
```

暴露工具：

- `scrollsnap_analyze_video`
- `scrollsnap_query_crops`
- `scrollsnap_compact_trace`
- `scrollsnap_parse_region`

## 方法

管线刻意保持专注和可解释：

1. 采样视频帧，用时间维运动能量检测主滚动区域。
2. 在局部证据支持时，把视口吸附到稳定容器边界。
3. 只在检测到的滚动视口内提取对齐特征。
4. 结合粗粒度行签名和局部密集匹配，估计相邻帧的垂直位移。
5. 通过分数、置信度阈值和上下文后处理，区分快速滚动与页面/场景切换。
6. 将位移积分为每个片段内的长页面坐标。
7. 按需生成长图拼接和带重叠的分块图。
8. 导出紧凑 trace，让下游 agent 在请求图像证据前先完成坐标查询。

热路径是有界的：视口检测只采样一部分帧；流式模式只保留相邻帧的对齐特征；使用 `--stream --no-images` 可以完全跳过长图拼接。

## Trace 契约

`trace.json` 是稳定的 API 边界：

- `trace_schema_version`
- `frame_count`, `fps`
- `viewport_bbox`
- `transitions`：相邻帧 `dy`、分数、置信度和切换标记
- `placements`：帧序号/时间到长页面坐标的映射
- `segments`：切分后的页面/场景片段
- `tiles`：可选局部分块图及其原始帧来源
- `quality`：聚合风险信号

图像文件是派生产物。生产 agent 可以只保留 `trace.json`，之后按需从原视频抽取原始帧裁剪。

## 评估结果

生成命令：

```bash
PYTHONPATH=src python3 -m scrollsnap.cli release-report \
  --out reports/release \
  --synthetic-frames 160 \
  --synthetic-repeats 3
```

报告环境：Python 3.13.5，macOS arm64。

### 摘要

发布报告是一份完整评估文档，不只是计时表。它覆盖评估流程、通过标准、场景覆盖矩阵、质量信号、token 预算假设、评测范围和有效性威胁。

核心结果：

- 直接合成重建：17/17 个场景通过。
- 场景覆盖：桌面基线、暂停、嵌套滚动容器、固定页内标题栏、反向滚动、页面跳转、快速滚动、噪声/压缩、重复列表、微小滚动、突发触控板滚动、超长页面、大视口、移动端比例、稀疏低纹理页面、表单/设置 UI、固定遮挡层。
- 吞吐：90.9-255.1 帧/秒，中位数 215.3 帧/秒。
- 视口吞吐：25.4-41.6 视口 MPix/s，中位数 31.1 MPix/s。
- 坐标准确性：中位平均 y 误差 0.00 px；最坏最大 y 误差 1.00 px。
- 视口边界准确性：L1 中位数 2.0 px；最大 L1 10 px。
- 质量风险标记：0 个合成场景，0 个浏览器场景。

通过标准为：片段数量精确匹配，视口 L1 <= 18 px，平均 y 误差 <= 3.5 px，最大 y 误差 <= 9 px。报告也记录了 `sparse` 场景中的 1 个低纹理孤立错配修正，没有把它隐式隐藏。

### Chromium 场景检查

正式报告还包含三段由 Chromium 渲染的本地页面录屏，用来检查浏览器真实渲染下的视口、切换和 token 预算。

| 场景 | 帧数 | FPS | 视口 L1 | 片段数 | 切换数 | 质量风险 | 相对逐帧节约 | 相对原生长图分块节约 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| browser_article | 48 | 68.8 | 1 | 1 | 0 | 无 | 93.4% | 45.9% |
| browser_dashboard | 48 | 61.1 | 4 | 1 | 0 | 无 | 93.4% | 36.3% |
| browser_table | 48 | 59.7 | 3 | 1 | 0 | 无 | 94.3% | 33.3% |

完整机器可读结果见
[`reports/release/release_benchmark.json`](reports/release/release_benchmark.json)，完整报告见
[`reports/release/evaluation_report.md`](reports/release/evaluation_report.md)。

## Token 节约估计

Token 估算器使用显式配置，口径接近 OpenAI 图像输入文档中常见的高细节分块计费方式：先按高细节规则约束图像尺寸，再估算：

```text
image_tokens = 85 + 170 * ceil(width / 512) * ceil(height / 512)
```

发布报告比较四种策略：

- 逐帧视口图：发送每一帧检测到的滚动视口图像
- 模型缩放后的长图：发送经过模型侧缩放后的长图
- 原始分辨率长页分块：保留完整长页面分辨率
- trace + 精选裁剪：紧凑 trace 加每个片段三个有代表性的原始帧证据裁剪

核心对比对象是逐帧视口图和原始分辨率长页分块。模型侧缩放后的长图在 token 数上可能很便宜，但对高页面无法保留像素级证据。

本版本在 Chromium 场景上的中位节约：

- 相对逐帧视口图：93.4%
- 相对原始分辨率长页分块：36.3%

逐帧基线已经偏保守，因为它发送的是检测到的视口裁剪，而不是全屏帧。

## 评测范围

本版本只报告项目实际跑过的评测：带完整重建真值的确定性合成录屏，以及三段由 Chromium 渲染的本地浏览器录屏。本版本不把任何外部数据集作为准确性评测基准。

## 局限

- 当前只支持垂直滚动重建。
- 不覆盖相机拍摄导致透视变形的视频。
- 滚动区域内部的大型动态遮挡层可能降低置信度。
- 几乎没有重叠的极高速滚动在信息论上存在歧义。
- 横向/双轴 canvas 应用需要单独建模。

## 仓库文件

- [`CHANGELOG.md`](CHANGELOG.md)：版本历史
- [`LICENSE`](LICENSE)：Apache-2.0
- [`CITATION.cff`](CITATION.cff)：研究引用元数据
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml)：测试与构建工作流

## 来源

- OpenAI 图像输入 token 计算：
  https://platform.openai.com/docs/guides/images-vision
