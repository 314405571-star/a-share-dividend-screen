# A 股分红质量筛选

**三个条件，前两个是算术，第三个只该是一张复核单。**

```
上市满 5 年
累计股息 / 融资总额 ≥ 3
没有原始股东大额减持、没有并购重组、没有卖壳
```

前两条是减法除法，第三条自动化不了：减持接口里没有"股东类型"字段，
而靠名字（`某某控股`、`某某投资`）猜"是不是原始股东"，正是自信的废话的来源。
所以它是一张**留空结论列的复核队列**，不是一个过滤器。

这个仓库真正补上的，是原脚本含糊带过的两件事：
**这个比值的单位到底是什么**，以及**公告扫描实际覆盖了多少天**。

核心是纯标准库，21 个测试，不联网也能跑。

[English](README.md) | [中文](README.zh-CN.md)

---

## 两个坑

### 1. 这个"比值"可能根本不是比值

`stock_history_dividend()` 返回的 `累计股息` 与 `融资总额` 都是裸数字。
如果两者都是**亿元**，这个商是真正的倍数——"公司用现金还回了三倍融资"。
如果 `累计股息` 是**百分比**，这个商没有任何物理意义，它只是一个排序分数。

原脚本自己的注释说它是百分比，却把这个商当作比值用。所以本仓库默认是诚实的：

```python
Units()                  # "mixed" → 这个 3 是代理分数，CSV 里会写明
Units.declared("yi")     # "same"  → 真正的倍数
```

```bash
python -m src.dividendscreen.akshare_source screen --dividend-unit yi
```

出池子之前，程序会先打印分布，让你去核对而不是去相信：

```
dividends median 67.5 · financing median 37.9 · quotient median 1.78 · p90 4.49
```

商的中位数落在 0.02 这种量级，基本可以断定两列不是一个单位。
需要严格口径请换 Tushare 的 dividend 接口，适配层只需要替换
`AkshareSource.companies()` 一个方法。

### 2. 公告扫描只看了 1,090 天里的 36 天

原脚本是"股票在外层、月份在内层"：

```python
while current <= end:
    ak.stock_notice_report(date=current)   # 返回的是"那一天全市场"的公告
    current += 30 天
```

两个后果。第一，同一个交易日的全市场公告被**每只股票**重新下载一遍——
50 只 × 36 个月 = 1,800 次请求，其中 1,764 次是重复的。
第二，步长是 30 天，三年只覆盖 36 个散点日期，发布在其它任何一天的公告都看不见，
而输出写的是"未扫描到命中关键词的公告"。

本仓库反过来：**按天遍历，每天拉一次，池内匹配**，并且把"失败天数"
和"没有公告的天数"分开统计。

---

## 快速开始

```bash
pip install -r requirements.txt

# 离线：60 家合成公司 + 假数据源，产出三个复核文件
python examples/demo_screen.py

# 测试（纯标准库）
python tests/test_pool.py
python tests/test_insiders.py
python tests/test_notices.py
python tests/test_pipeline.py
```

联网（akshare）：

```bash
python -m src.dividendscreen.akshare_source screen \
    --dividend-unit yi --notice-days 365 --out output
```

---

## 离线 demo 的输出

```
universe 60  ·  units: same (comparable)
  dividends median 67.5 · financing median 37.9 · quotient median 1.78 · p90 4.49
  total             60
  too_young         31
  no_financing      14
  no_dividend        2
  below_ratio        3
  selected          10
  reduction feed: 6 rows, median |shares| = 1,075.0, 50.0% above 1000
  large reductions in the pool: 3 rows
  notices: 61/61 days, coverage 100.0%, 2 hits
```

`output/` 下三个文件：

| 文件 | 谁填 |
|---|---|
| `初筛池_<日期>.csv` — 满足条件一二，附比值与口径 | 自动 |
| `减持清单_<日期>.csv` — 大额减持，**`人工结论` 列留空** | **人** |
| `公告疑点_<日期>.csv` — 命中的公告标题，同样留空 | **人** |

复核标准写在 [docs/算法总结.md](docs/算法总结.md) 第 5 节：
股东是不是原始股东、这笔减持算不算大额、公告是不是真的重组或卖壳。

---

## 修了哪些 bug

原始脚本逐字保留在 [`legacy/`](legacy/)。

| # | 缺陷 | 后果 | 修复 |
|---|---|---|---|
| 1 | 公告扫描按月跳跃 | 1,090 天只看 36 天，其余公告不可见，输出却像"没问题" | 按天遍历 |
| 2 | 每只股票重复下载同一天公告 | 1,800 次请求，98% 是重复 | 每天一次，池内匹配 |
| 3 | 请求失败被 `except: continue` 吞掉 | 扫描有洞但看不出来 | 统计失败天数与覆盖率 |
| 4 | 比值单位靠注释约定 | 阈值 3 在两种口径下含义完全不同 | 显式 `Units`，写进 CSV |
| 5 | "大额"只看股数 | 1000 万股 = 5000 万到 10 亿 | 股数 **或** 占总股本比例 |
| 6 | `5×365` 天 + `datetime.now()` | 闰年差一天；结果随运行时间漂移 | 按整年回退，`as_of` 显式传入 |
| 7 | 代码列 `astype(str)` | 浮点代码变成 `0001.0` | 去小数、补零 |
| 8 | 人工步骤只存在于 print | 没有东西可以交给复核的人 | 三个 CSV，人工列留空 |

---

## 目录结构

```
.
├── src/dividendscreen/
│   ├── pool.py               # 条件一二、单位、漏斗（纯函数）
│   ├── insiders.py           # 减持阈值与复核行
│   ├── notices.py            # 按天扫描、关键词匹配、覆盖率
│   └── akshare_source.py     # 适配层 + CLI
├── examples/
│   ├── demo_screen.py        # 合成市场 + 假数据源
│   └── output/               # 三个复核文件（生成）
├── legacy/screen_v1.py       # 原始脚本，未改动
├── docs/算法总结.md
├── tests/
└── requirements.txt
```

---

## 诚实的局限

- **不是回测。** 没有买点、卖点、成本。"肯分钱的公司"不等于"会涨的股票"。
- **第三条无法自动化。** 没有股东类型字段，公告必须读原文。
- **减持数据不完整。** `stock_ggcg_em` 只返回近期记录，清单为空 ≠ 没有减持。
- **标题是粗筛。** "股份转让"很常见也很无害；"发行股份购买资产"又不含任何关键词。
  所以命中要读，没命中也别当安全。
- **口径依赖数据源。** 严格的分红/融资金额比需要 Tushare 或手工导出。
- **五年门槛会砍掉很多好公司**，这是设计选择。

---

## 声明

仅供研究与学习，**不构成投资建议**。

## 许可证

MIT
