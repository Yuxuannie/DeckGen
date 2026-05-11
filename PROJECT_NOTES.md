# DeckGen 项目笔记

> 这份文档是 DeckGen 的长期记忆。每次重要发现、修复、决策都追加到这里。
> 不要重写已有内容。新发现写到对应章节末尾或新增章节。
> 每条记录附日期 + 谁验证过（Yuxuan / Claude Code）。

## 1. 项目目标

DeckGen 是 MCQC v3.5.5 (`scld__mcqc.py`) 的下一代替代，用于从 Liberate
characterization kit 生成 SPICE deck 文件。需要复刻 MCQC 全部生成能力 +
增加现代 GUI 体验。

MCQC 源码（参考实现，不在 DeckGen repo 内）:
`/CAD/stdcell/DesignKits/Sponsor/Script/MCQC_automation/Tool_home/deck_generation/v3.5.5/scld__mcqc.py`

## 2. Template.tcl 关键事实（已验证）

> 验证日期: 2026-05 (Yuxuan)

template.tcl（== Liberate characterization kit 主文件）是 DeckGen 的核心输入。
关于它的事实清单——这些都被实测确认，不是推测：

### 2.1 -type 分布（来自 76k+ define_arc 统计）

| -type | 数量 | 性质 |
|-------|------|------|
| hidden | 76,419 | 输入跳但输出不跳，喂 power/leakage |
| min_pulse_width | 6,002 | MPW 约束 |
| setup | 3,092 | setup 约束 |
| hold | 3,092 | hold 约束 |
| async | 2,376 | preset/clear |
| edge | 1,812 | clock edge |
| (无 -type) | 大量 | **combinational delay arc**，timing 主体 |
| 其他 | 少量 | non_seq_*, removal, recovery, enable, disable |

**关键陷阱**: `grep -type` 看不到无 -type 的 define_arc。0-arc bug 的根因。

### 2.2 Combinational delay arc 的判别

无 -type 的 define_arc = combinational delay arc。MCQC 的 parser 做法
（`charTemplateParser/funcs.py:477-482`）:
```python
if "type" not in arc:
    arc['type'] = 'combinational'
```

DeckGen parser 必须 mirror 这个 default 行为。

### 2.3 Vector 编码 cross-validation

vector 字段（`{Rxxx}` / `{xxRR}` 等）每个字符对应 pinlist 一个 pin 的跳变方向：
- `R` = rise, `F` = fall, `x` = static
- 字符位置 == pinlist 位置

**输出位是否跳变可以反推 arc 类型**:
- 输出位 = `x` → input 跳输出锁，必为 hidden（power 用）
- 输出位 = `R`/`F` → 输出跳变，必为 combinational delay

这是独立于 `-type` 的判别信号。Parser 应同时检查两者，不一致就 warning。

### 2.4 AIOI21 cell ground truth (黄金验证样本)

Cell: `AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD`
Function: `ZN = B · !(A1·A2)`
template.tcl 段落: 见 ALAPI_active_cell block

| 类别 | 数量 | 备注 |
|-----|------|------|
| define_leakage | 8 | 8 input states 全覆盖 |
| define_arc total | 24 | |
| - -type hidden | 14 | 6 (A1) + 6 (A2) + 2 (B) |
| - 无 -type (delay) | **10** | |

10 条 delay arc 完整列表:
| # | -related_pin | -when | -vector | .lib 对应 |
|---|---|---|---|---|
| 1 | A1 | (none) | `{FxxR}` | A1->ZN, cell_rise |
| 2 | A1 | (none) | `{RxxF}` | A1->ZN, cell_fall |
| 3 | A2 | (none) | `{xFxR}` | A2->ZN, cell_rise |
| 4 | A2 | (none) | `{xRxF}` | A2->ZN, cell_fall |
| 5 | B  | "A1&!A2"   | `{xxRR}` | B->ZN @ A1&!A2, rise |
| 6 | B  | "A1&!A2"   | `{xxFF}` | B->ZN @ A1&!A2, fall |
| 7 | B  | "!A1&A2"   | `{xxRR}` | B->ZN @ !A1&A2, rise |
| 8 | B  | "!A1&A2"   | `{xxFF}` | B->ZN @ !A1&A2, fall |
| 9 | B  | "!A1&!A2"  | `{xxRR}` | B->ZN @ !A1&!A2, rise |
| 10 | B | "!A1&!A2"  | `{xxFF}` | B->ZN @ !A1&!A2, fall |

合并为 5 条 .lib timing arc（A1, A2, B x 3 conditional）。

A1/A2 无 -when 因为它们只有一种敏化条件（side input = 1 全部）。
B 必须按 state 拆 -when，因为不同 state 在物理 CMOS 上对应不同 RC 路径。

### 2.5 物理直觉（为什么 B 要拆 3 条）

`ZN = B * !(A1*A2)` 的 PMOS 上拉网络: `(A1-P || A2-P) -- B-P` 串联结构。
B 上跳时 PMOS 导通路径电阻取决于 A1/A2 state:
- `!A1 & !A2`: 两 PMOS 并联 -> R/2 -> 最快
- `A1 & !A2` / `!A1 & A2`: 单 PMOS -> R -> ~2x 慢（拓扑等价，分两条是因为 STA 按 boolean state 查表）
- `A1 & A2`: 不导通，B 跳无效（-> hidden arc，不进 timing）

A1/A2 各只有一种敏化 state，所以一条 unconditional arc 就够。

## 3. MCQC 输入源参考

> 验证日期: 2026-05 (Yuxuan)

MCQC `--char_type non_cons` 路径生成 combinational delay deck。globals.cfg 关键字段:

| 字段 | 路径示例 | 用途 |
|------|---------|------|
| template_deck_path | `.../FMC_template/templateFileMap/` | SPICE deck 骨架 |
| template_lut_path | `.../FMC_template/` | LUT axes 定义 |
| kit_path | `.../Collaterals/kits/` | **template.tcl 所在地** |
| user_model_file | `.../cln2p_sp_v1d0_2p1_usage.l` | SPICE model |
| waveform_file | `.../std_wv_c651.spi` | 输入波形 |
| cell_pattern_list | `"INVMDLI... ND2MDLI... AOI33M1L..."` | 手写 cell 名单 |
| valid_arc_types_list | `"delay"` 或 `"setup hold removal ..."` | 过滤 arc type |

`--char_type non_cons` 配 `valid_arc_types_list = "delay"` 跑组合逻辑。
`--char_type cons` 配多个 constraint type 跑时序约束。

## 4. 已修复 bug 历史

### 2026-05-01: JS SyntaxError (GUI 无法加载)
- 现象: 浏览器 console 报 `Uncaught SyntaxError: Invalid or unexpected token`，GUI 卡在 Loading
- 根因: HTML_PAGE 是 Python `"""` 字符串，JS 里的 `\n` 被 Python 解释为真实换行
- 修复: 6 处 JS string literal 的 `\n` 改为 `\\n`
- 验证: Mac + Linux 均可正常加载 (Yuxuan)

### 2026-05-01: 3 小时 GUI 挂起
- 现象: 首次加载 GUI 挂起 3 小时
- 根因: CollateralStore 自动 rescan 22 个 lib 的 Netlist 目录
- 修复: GUI 使用 `skip_autoscan=True`，去掉 prewarm 线程
- 验证: 加载时间降至秒级 (Claude Code)

### 2026-05-02: 0-arc 解析 bug
- 现象: `cells found = 0, arcs found = 0` 对所有 cell
- 根因: parser 用 `flags.get('-type', '')` 留空字符串，MCQC 的 default 是 `'combinational'`
- 修复: parser 遇到无 -type 的 define_arc 时 default 设 'combinational'，对齐 MCQC `funcs.py:477`
- 验证 cell: AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD 应产 10 deck

### 2026-05-02: ALAPI 格式 parser 不支持
- 现象: 旧 parser 用 Liberty 格式 regex，ALAPI 格式完全不匹配
- 根因: ALAPI 的 define_cell/define_arc 用 `-flag value` 命令行语法 + 末尾 positional cell name
- 修复: 新增 ALAPI 格式自动检测 + 完整 parser（续行合并、Tcl tokenizer、flag 解析）
- 验证: 合成测试通过，222 existing tests pass (Claude Code)

### 2026-05-01: Debug print cleanup
- 现象: stderr 被 [batch], [resolver], [arc_info], [generate_v2] 调试输出污染
- 修复: 删除全部临时 debug print 语句及其 inline `import sys`
- 验证: grep 无残留 (Claude Code)

## 5. 待办 feature

- [x] Source quick-link: [tcl] [net] buttons on arc rows (2026-05-02)
- [x] Vector-based arc 分类 sanity check (2026-05-02)
- [x] Deck 列表按 (related_pin, when) 分组折叠展示 (2026-05-02)
- [x] AIOI21 ground truth 自动化测试 (2026-05-02, 12 assertions)
- [x] MCQC-parity template selection: 688+ hold/setup/mpw rules (2026-05-02)
- [x] Collateral-backed deck generation with auto-resolved netlist/model/waveform (2026-05-02)
- [x] LUT grid picker: inline per arc-type, Shift+click rectangle, preset buttons (2026-05-02)
- [x] Monaco Editor inline source viewer with Tcl/SPICE syntax highlighting (2026-05-02)
- [x] i1/i2 table-point index lookup from template.tcl in batch generate (2026-05-02)
- [x] arc_id parse: ALAPI combinational vector direction mapping fix (2026-05-02)

### 2026-05-02: Generate NetworkError

**现象**: 点 "Generate 25 decks" 后前端报 NetworkError，无响应

**诊断步骤结果**:
- Step 1 (DevTools): 未实测（先做代码层诊断）
- Step 2 (curl backend): N/A
- Step 3 (backend logs): N/A
- Step 4 (单点测试): N/A
- Step 5 (CORS): 不适用（同源）
- Step 6 (协议): 同源 http

**根因**: arc_id 格式破损导致 parse 全部失败

根因链：
1. ALAPI combinational arc 的 `_vector_to_dirs()` 对 4 字符 vector (如 `FxxR`)
   返回空 `pin_dir` 和/或空 `rel_pin_dir`
2. GUI JS `buildArcId()` 用 `join('_')` 拼接，空段 → 双下划线 `__`
   实际产出: `combinational_AIOI21..._ZN__A1__NO_CONDITION`
3. 后端 `parse_arc_identifier()` 按 `_` 分割，空段偏移所有字段 → 返回 None
4. `plan_jobs` 收集 "Cannot parse" error，0 个 job 产出
5. `_handle_generate_v2` 发空 done 行或异常 → 前端 fetch stream 中断 → NetworkError

**修复方案**:
1. `_vector_to_dirs()` 改为用 pinlist 位置映射正确解析 4 字符 vector
2. `buildArcId()` 对空 dir 使用 fallback 值 (如 'any')
3. `_api_list_arcs()` 确保返回的 probe_dir/rel_dir 非空

验证: AIOI21 arc_id 应为 `combinational_AIOI21..._ZN_fall_A1_rise_NO_CONDITION_1_1`

## 7. GUI Features

### 2026-05-02: Inline LUT Grid Picker
- Replaces modal overlay with inline clickable grid per arc-type
- Rows = index_1 (i1), Cols = index_2 (i2), values from template.tcl
- Single-click toggle, Shift+click rectangle selection
- Preset buttons: Full / Diag / Corners update grid visually
- Hidden "Advanced" text input syncs bidirectionally with grid
- Grid dimensions from arc's actual index_1/index_2 arrays

### 2026-05-02: Monaco Editor Source Viewer
- Monaco Editor 0.45.0 from jsDelivr CDN (read-only mode)
- Backend: `/api/source/register`, `/api/source/<id>`, `/api/source/<id>/find_definition`
- File access restricted to COLLATERAL_ROOT (no arbitrary file read)
- Lazy loading: files >5000 lines load in chunks (target ±500 lines initially)
- Cross-reference: ctrl+click on template names (after `-delay`, `-constraint`, etc.)
  calls `find_definition` endpoint, jumps to `define_template` line
- History stack (10 deep) for Back/Forward navigation
- Goto line via Ctrl+G or footer button
- Left-click [tcl]/[net] opens viewer; right-click copies vscode:// URL
- Tcl syntax highlighting for template.tcl, SPICE for netlists
- Known limitation: cross-reference is text-level token match, not semantic Tcl parse;
  duplicate template names jump to first occurrence

## 6. 参考资料

- AOI21 PMOS pull-up 物理推导: 见 conversation log（2026-05）
- MCQC parser `arc['type'] = 'combinational'` default: `charTemplateParser/funcs.py:477-482`
- DeckGen ALAPI parser 入口: `core/parsers/template_tcl.py` `_parse_alapi_full()` line ~196
- MCQC checkValidArc delay 展开: `qaTemplateMaker/funcs.py:750-764`
