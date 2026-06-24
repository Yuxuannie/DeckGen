# Library Audit —— 详细测试指南（真实数据 / Linux）

引擎从 LPE `.subckt` 拓扑**独立推导**每条组合弧的敏化区域，并与 kit 的 `-when`
做**区域等价**比对，输出分群报告：TRUST（MATCH）vs FLAGGED（DIVERGENCE /
UNSUPPORTED-WHEN / ERROR）。本指南教你在 Linux 上对真实 library 跑这套审计，并把
结果反馈回来。

分支：`claude/lucid-noether-cat8lr`。引擎核心 **纯 stdlib，无需 pip**。

---

## 0. 拉取最新代码

```bash
cd /path/to/DeckGen
git fetch && git checkout claude/lucid-noether-cat8lr && git pull
```

Python 用 **python3.12**（测试同此）。无需安装任何依赖。

---

## 1. 安装自检（30 秒，无需真实数据、无需浏览器）

先确认工具在你机器上能跑出已知结果，再碰真实数据：

```bash
python3 -c "from core.library_audit import audit_from_paths; import json; \
r=audit_from_paths('tests/fixtures/audit_lib/template.tcl','tests/fixtures/audit_lib/netlist'); \
print(json.dumps(r['summary'],indent=2))"
```

**期望输出**（一字不差）：

```json
{ "cells": 4, "arcs": 6, "match": 3, "divergence": 1,
  "unsupported": 1, "error": 1, "flagged": 3 }
```

可选：`python3.12 -m pytest tests/test_library_audit.py -q` → `9 passed`。

如果这一步就出错，把报错贴我 —— 是环境问题，不是数据问题。

---

## 2. 放置真实 collateral（层级 = DeckGen v1.0）

> `gui.py` **没有** `--collateral` 参数：collateral 根目录固定为 `gui.py` 同级的
> `collateral/`。真实库放这里，或软链过来。

必须的层级：

```
collateral/<NODE>/<lib_type>/
    Netlist/LPE_<corner>/<cell>.spi      <- LPE 网表（引擎唯一输入，红线 A）
    Template/<...>.template.tcl           <- kit 的 -when（被审计对象）
    Char/<...>.tcl                        <- corner 发现用
```

真实例子：

```
collateral/N2P_v1.0/tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i/
    Netlist/  Template/  Char/
```

库在别处就软链，不用复制：

```bash
ln -s /CAD/.../realib  collateral/N2P_v1.0
```

---

## 3. 跑审计 —— 二选一

### 3A. GUI（你 v1.0 用过的方式）

- 有桌面浏览器的机器：
  ```bash
  python3 gui.py            # http://127.0.0.1:8585
  python3 gui.py --port 9090
  ```
- **无头服务器**（airgap server 常见，`gui.py` 只绑 127.0.0.1）：
  ```bash
  # 服务器上：
  python3 gui.py --no-browser --port 8585
  # 你笔记本上做 SSH 端口转发，再用本地浏览器开 http://127.0.0.1:8585
  ssh -L 8585:127.0.0.1:8585 user@server
  ```
- 操作：**Explore** 标签选 node + lib_type（首次会自动建 `manifest.json`，大库可能几十秒）
  → 切到 **Library Audit** 标签 → 选 corner → **Run library audit**。

### 3B. 纯命令行 / 批量（推荐用于大库或纯服务器，无需浏览器）

```bash
# 1) 发现可用 corner：
python3 -c "from core.collateral import CollateralStore as C; \
print(C('collateral','N2P_v1.0','<lib_type>').list_corners())"

# 2) 跑审计，summary 打屏 + 完整报告写 audit.json：
python3 -c "from core.library_audit import audit_combinational_library as A; import json; \
r=A('collateral','N2P_v1.0','<lib_type>','<corner>'); \
json.dump(r, open('audit.json','w'), indent=2); print(json.dumps(r['summary'],indent=2))"
```

把 `audit.json` 或屏幕上的 summary 发我即可。

**先抽样几个 cell**（大库提速 / 定点排查）：

```bash
python3 -c "from core.library_audit import audit_combinational_library as A; import json; \
r=A('collateral','N2P_v1.0','<lib_type>','<corner>', cells=['<CELL1>','<CELL2>']); \
print(json.dumps(r,indent=2))"
```

---

## 4. 怎么读报告

`summary`：`cells / arcs / flagged / divergence / unsupported / error / match`。

**FLAGGED 优先看**（按重要性已排序，置顶）：

| 状态 | 含义 | 你要做的 |
|------|------|----------|
| **DIVERGENCE** | 引擎推的区域 ≠ kit `-when` | 看 `missing`（kit 漏的敏化态）/ `extra`（kit 多标的屏蔽态）。这要么是**真 CATCH（kit 写错）**，要么是引擎要改进 —— 发我判断。 |
| **UNSUPPORTED-WHEN** | kit `-when` 含 OR 等非合取式 | 引擎诚实弃权（不是错）。记下来，后续可扩展。 |
| **ERROR** | 该 cell 网表没解析出 / 推导失败 | 看 `detail`；常是网表路径或格式问题。 |

每条 FLAGGED 还带：`SENSITIZING`（带 ↑/↓ 输出方向 + `SIG` 导通签名）、`BLOCKED`、
`partition`（“引擎认为该拆但 kit 没拆”提示）、`kit -when` 原文。

`TRUST`（MATCH）折叠收纳 —— 引擎确认 kit 正确的弧。

---

## 5. 关键认知（避免误解）

- **区域审计是“拓扑”级，与 corner / PVT 无关**。corner 只决定读哪个 LPE 网表目录。
  所以随便选一个**有 LPE 网表**的 corner 即可；换 corner 不会改变 region / verdict。
- 引擎**只从 `.subckt` 推**（红线 A）。kit `-when` 是被审计对象，不参与推导 ——
  所以“引擎说 DIVERGENCE”意味着拓扑和 kit 不一致，值得人看。
- 合成单元只证明**方法对**；真正的价值（impact）是真实库上的一条 **DIVERGENCE/CATCH**。

---

## 6. 把什么反馈给我（决定下一步）

按价值从高到低：

1. **任意一条 DIVERGENCE**：`cell 名` + 它的 `.subckt` 片段 + 那几条 kit `-when`。
   我据此判定是“真 CATCH（kit 错）”还是“引擎需改进”。**一条真 CATCH 胜过 100 条合成 MATCH。**
2. `summary` 截图，或 `audit.json`。
3. 工具的**报错信息**（尤其层级不匹配 / 解析失败）—— 那是真实层级的最后一公里。

---

## 7. Troubleshooting

| 现象 | 处理 |
|------|------|
| `manifest.json not found` | 先建：`python3 tools/scan_collateral.py --node N2P_v1.0 --lib_type <lib> --collateral_root collateral` |
| 报告 `arcs: 0` | 该库的 `define_arc` 可能不是组合（无 `-type`）弧，或 template 非 ALAPI 格式。把一个 cell 的 `template.tcl` 片段发我。 |
| 全是 `ERROR` | 网表没找到。确认 `Netlist/LPE_<corner>/<cell>.spi` 存在且文件名与 cell 名一致（支持后缀 `_c_qa.spi`/`_c.spi`/`.spi`）。把一个 cell 的网表目录 `ls` 结果发我。 |
| 大库很慢 | 用 3B 的 CLI + `cells=[...]` 抽样；或先单 sublib 跑。 |
| 解析 / 编码错误 | 直接贴报错；可能是真实 template 的某语法分支没覆盖。 |

---

## 附：本工具做了什么 / 没做什么（诚实边界）

- **做了**：组合 cell 的敏化区域推导 + 区域等价审计 + 分群报告；多输出 cell 按
  `-vector` 正确分配到各输出。
- **没做（暂）**：deck 字节级生成对比（你说过不要 byte-equal）；时序 cell（research 线，单独分支）；
  kit `-when` 含 OR 的判定（标 UNSUPPORTED 而非误判）。
