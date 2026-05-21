# PaperGuard

> 学术论文数据/图像/统计异常筛查工具。
> **只标记异常，不指控造假。** 每条 Finding 都附带可能的合法解释。

![status](https://img.shields.io/badge/status-2.1.5-blue)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![tests](https://img.shields.io/badge/tests-372%20passing-brightgreen)
![detectors](https://img.shields.io/badge/detectors-33-blue)
![license](https://img.shields.io/badge/license-MIT-green)

[English README](README.md) · 中文 README · **[🤗 在线 Demo](https://huggingface.co/spaces/exergyleizhou/paperguard-demo)**

## 重要立场

**PaperGuard 标记的是统计/图像异常，不构成对作者的造假指控。**

异常可能源自仪器特性、数据处理流程、合理的实验设计或诚实错误。
对作者诚信的任何质疑都应通过期刊编辑或机构调查渠道进行，而不应
单凭本工具的输出。

每条 Finding 都包含至少 3 条 `innocent_explanations`（可能的合法解释）。

## 33 个内置检测器

| 类别 | IDs |
|---|---|
| 数字取证 | A1（末位）、A2（Benford）、A3（列间算术）、A5（小数）、A6（不可能值）、A7（末位 0/5 专项） |
| 摘要统计一致性 | B1（GRIM）、B4（statcheck）、B5（TIVA）、B6（GRIMMER）、B7（p-curve）、B8（SPRITE） |
| 临床试验 | C1（Carlisle 基线平衡） |
| 方差结构 | D1（残差平滑）、D2（缺失值模式）、E1（ICC 独立性,2.0.14 新增） |
| 图像取证 | F1（pHash 跨图）、F2（ORB 图内复制）、F3（块统计 splice）、F4（跨论文 pHash 库）、F5（EXIF 跨图聚类） |
| 元数据 | G1（图像 EXIF 时序）、G3（docx rsid）、G4（文件元数据） |
| 论文工厂 | M1（合作者图谱） |
| 文本与试验 | T1（n-gram 剽窃）、T2（NCT outcome 漂移）、T3（数据/伦理审计）、T4（论文工厂扭曲短语）、T5（Stapel 语言指纹） |
| **LLM 文本(新)** | **T6（词面字典 + 动态字典）、T7（续写困惑度 proxy)、T8（DetectGPT-curvature)** |

### 实证标定(诚实)

| 检测器层 | 数据集 | LR+ | 解读 |
|---|---|---|---|
| T6 lexical(默认阈值) | v8/v9 N=85,Nature-tier 已发表撤稿 | ~0 | T6 是**投稿前/预印本**筛查信号,不是 post-publication 取证;copy-editing 抹除了字典命中。 |
| B4 statcheck(N=41 ground-truth) | crossval_statcheck | recall 100%, 决策翻转 recall 94% | 与 Nuijten 2016 原版 statcheck 协议一致。 |
| F1/F4 image | recall_image_v1 N=15+15 | LR+ 表见 `docs/recall_image_v1.md` | 图像 pHash 复用层。 |
| T7 / T8 | (待 GPT-4o-class endpoint 配置) | — | 单元测试覆盖;实测延后到 logprobs-capable endpoint 可用时。 |

详见 `docs/fraud_case_studies.md`：每个真实造假案例（Stapel / Fujii /
Hwang / Schön / Macchiarini / Wansink / Masliah / 耿同学打假对象 /
Bik 2016）对应触发的检测器。

## 安装

```bash
git clone <repo>
cd PaperGuard
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -e ".[dev]" types-openpyxl
```

## 使用

### 扫描本地文件

```bash
paperguard scan -f data.xlsx
paperguard scan -f paper.pdf --doi 10.xxx --output-html report.html --lang zh-CN
paperguard scan -f manuscript.docx --output-json report.json
```

### 用 DOI 自动从 Unpaywall 拉 OA PDF

```bash
paperguard scan --doi 10.1038/xxx   # 自动下 OA PDF 后扫描
```

### 批量

```bash
paperguard batch --glob 'papers/*.pdf' --out-dir reports/
```

### Web UI（匿名单用户）

```bash
pip install paperguard[webui]
paperguard webui --port 8765
# 浏览器打开 http://127.0.0.1:8765/
```

### Web UI（多租户,可选启用）

PaperGuard 2.0 在 `/app/*` 提供**邀请制多租户**功能:用户账号、持久化项目、
带可见性的扫描报告(`private`/`org`/`public`)、管理员邀请流程。

```bash
pip install paperguard[webui]

export PAPERGUARD_MULTITENANT=1
export PAPERGUARD_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export PAPERGUARD_ADMIN_EMAIL="admin@your-org.example"
export PAPERGUARD_ADMIN_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(24))')"

paperguard webui --port 8765
# 浏览器打开 http://127.0.0.1:8765/app/login
```

仅在设置 `PAPERGUARD_DB_URL` 或 `PAPERGUARD_MULTITENANT=1` 时启用,否则
行为与 1.x 完全一致。默认 SQLite,可通过 URL 切换 PostgreSQL/MySQL。
完整文档见 [`docs/webui_multitenant.md`](docs/webui_multitenant.md)。

### LLM 解释（可选）

```bash
$env:PAPERGUARD_LLM_PROVIDER="anthropic"
$env:ANTHROPIC_API_KEY="sk-..."
paperguard explain --json report.json --finding-index 0
```

### 工具命令

```bash
paperguard selfcheck                       # 自检安装
paperguard diff before.json after.json     # 对比两次扫描
paperguard search --author "Watson J"      # OpenAlex 作者搜索
```

## 多语言支持

通过 `--lang` 或环境变量 `PAPERGUARD_LANG` 切换：

- `en` 英文（默认）
- `zh-CN` 中文
- `es` 西班牙文
- `ja` 日文
- `de` 德文

## 插件系统

通过 Python entry point 注册第三方检测器：

```toml
[project.entry-points."paperguard.detectors"]
my_detector = "my_pkg.detectors:MyDetector"
```

参考模板：[`examples/03_custom_detector.py`](examples/03_custom_detector.py)。

## 测试与开发

```bash
pytest -m "not network" -v
ruff check src/ tests/
mypy src/
```

`tests/test_golden.py` 把对内置 fixture 的检出数固化为防退化闸门。

## 数据来源（用户自带）

某些检测器需要本地 CSV，不内置数据：
- **Retraction Watch**：`paperguard.fetcher.retraction_watch.lookup_retraction(doi, csv_path)`
- **ORI Administrative Actions**：`paperguard.fetcher.ori_sanctions.lookup_author(name, csv_path)`

公开数据从对应官网下载到本地 `cache_dir/`。

## License

MIT
