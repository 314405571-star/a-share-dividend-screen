import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

# ============================================================
# 条件一：上市满 5 年
# 条件二：分红融资代理比 ≥ 3（相对口径，非绝对金额口径）
# 条件三：初筛池逐只输出减持股东清单，人工判断原始股东大额减持；
#          同时扫描并购/重组/套现类公告，结果人工复核
# ============================================================

# ---------- 1. 初筛：条件一 + 条件二（全市场一次性完成） ----------
print("拉取全市场历史分红数据...")
div_df = ak.stock_history_dividend()

div_df["上市日期"] = pd.to_datetime(div_df["上市日期"], errors="coerce")
cutoff = datetime.now() - timedelta(days=5 * 365)

base = div_df[div_df["上市日期"] <= cutoff].copy()
base = base[
    (base["融资总额"] > 0)
    & (base["分红次数"] > 0)
    & (base["累计股息"] > 0)
].copy()

# 注意：累计股息单位是 %，融资总额单位是亿元；此比值为代理指标，非绝对金额比
base["分红融资代理比"] = base["累计股息"] / base["融资总额"]
initial_pool = base[base["分红融资代理比"] >= 3].copy()

initial_pool["代码"] = initial_pool["代码"].astype(str).str.zfill(6)
print(f"初筛（上市满5年 + 分红融资代理比 ≥ 3）：{len(initial_pool)} 只")
print(initial_pool[["代码", "名称", "上市日期", "累计股息", "融资总额", "分红融资代理比"]].to_string(index=False))


# ---------- 2. 条件三-A：小池子逐只拉取减持记录，输出股东名称供人工判断 ----------
# stock_ggcg_em 返回的字段包括：stock_code、stock_name、holder_name（股东名称）、
# change_num（变动数量）、change_num_symbol、change_total_ratio、start_date、notice_date 等
# 该接口没有直接的“股东类型”字段，无法自动判断“原始股东”，
# 因此这里只负责把“大额减持”记录中的股东名称提取出来，由人工对照判断。

print("\n拉取全市场股东减持数据（用于小池子匹配）...")
reduce_df = ak.stock_ggcg_em(symbol="股东减持")

# 字段兼容处理
code_col = None
for c in ["stock_code", "代码", "股票代码"]:
    if c in reduce_df.columns:
        code_col = c
        break

holder_col = None
for c in ["holder_name", "股东名称"]:
    if c in reduce_df.columns:
        holder_col = c
        break

amount_col = None
for c in ["change_num", "变动数量", "持股变动信息-变动数量"]:
    if c in reduce_df.columns:
        amount_col = c
        break

date_col = None
for c in ["notice_date", "公告日期", "变动截止日期"]:
    if c in reduce_df.columns:
        date_col = c
        break

if not all([code_col, holder_col, amount_col]):
    raise ValueError(f"减持接口字段不完整，当前列：{list(reduce_df.columns)}")

reduce_df["_code"] = reduce_df[code_col].astype(str).str.zfill(6)
reduce_df["_amount"] = pd.to_numeric(reduce_df[amount_col], errors="coerce")

# “大额减持”阈值可按需调整：此处设为单次变动数量绝对值 ≥ 1000 万股
LARGE_REDUCE_THRESHOLD = 1000  # 万股
large_reduce = reduce_df[reduce_df["_amount"].abs() >= LARGE_REDUCE_THRESHOLD].copy()

# 只保留初筛池中的股票
pool_codes = set(initial_pool["代码"])
large_reduce_pool = large_reduce[large_reduce["_code"].isin(pool_codes)].copy()

if date_col:
    large_reduce_pool[date_col] = pd.to_datetime(large_reduce_pool[date_col], errors="coerce")
    large_reduce_pool = large_reduce_pool.sort_values(["_code", date_col], ascending=[True, False])


# ---------- 3. 输出每只初筛股票的“大额减持股东清单” ----------
print("\n" + "=" * 80)
print("条件三-A：初筛池中大额减持（单次 ≥ 1000 万股）的股东名称清单")
print("请人工对照股东名称，判断是否属于“原始股东 / 控股股东 / 实控人”的大额减持")
print("=" * 80)

for _, row in initial_pool.iterrows():
    code = row["代码"]
    name = row["名称"]
    sub = large_reduce_pool[large_reduce_pool["_code"] == code]

    if sub.empty:
        continue

    print(f"\n{code} {name}")
    print("-" * 60)
    for _, rec in sub.iterrows():
        parts = [f"股东：{rec[holder_col]}", f"变动数量：{rec[amount_col]} 万股"]
        if "change_total_ratio" in rec.index:
            parts.append(f"占总股本：{rec['change_total_ratio']}%")
        if date_col and pd.notna(rec[date_col]):
            parts.append(f"公告/变动日期：{rec[date_col].strftime('%Y-%m-%d')}")
        print("  |  ".join(parts))

# 如果你希望把清单导出为 Excel 供线下逐条标记，取消下面注释：
# large_reduce_pool_out = large_reduce_pool[[code_col, "stock_name", holder_col, amount_col]].copy()
# large_reduce_pool_out.columns = ["代码", "名称", "股东名称", "变动数量(万股)"]
# large_reduce_pool_out.to_excel("初筛池_大额减持股东清单.xlsx", index=False)


# ---------- 4. 条件三-B：小池子逐只扫描并购 / 重组 / 套现类公告标题 ----------
# 该步骤只在小池子上执行，扫描结果作为“疑点清单”输出，不直接自动剔除，
# 由人工结合公告内容判断是否属于应当排除的情形。

MA_KEYWORDS = ["并购", "重大资产重组", "收购", "资产重组", "借壳", "卖壳"]
CASH_OUT_KEYWORDS = ["清仓式减持", "协议转让", "股份转让", "大额套现"]

def scan_bad_announcements(stock_code: str, stock_name: str, days_back: int = 1080) -> list:
    """扫描近 days_back 天内与并购/重组/套现相关的公告标题，返回命中列表。"""
    hits = []
    end = datetime.now()
    start = end - timedelta(days=days_back)
    current = start

    while current <= end:
        date_str = current.strftime("%Y%m%d")
        try:
            notice = ak.stock_notice_report(date=date_str)
        except Exception:
            current += timedelta(days=30)
            continue

        if notice is None or notice.empty:
            current += timedelta(days=30)
            continue

        code_col_n = None
        for c in ["代码", "股票代码", "证券代码"]:
            if c in notice.columns:
                code_col_n = c
                break

        title_col = None
        for c in ["公告标题", "标题", "名称"]:
            if c in notice.columns:
                title_col = c
                break

        if code_col_n and title_col:
            sub = notice[notice[code_col_n].astype(str).str.zfill(6) == stock_code]
            for _, rec in sub.iterrows():
                title = str(rec[title_col])
                for kw in MA_KEYWORDS + CASH_OUT_KEYWORDS:
                    if kw in title:
                        hits.append({
                            "代码": stock_code,
                            "名称": stock_name,
                            "日期": date_str,
                            "公告标题": title,
                            "命中关键词": kw,
                        })
        current += timedelta(days=30)  # 按月跳跃，避免逐日请求过频

    return hits

print("\n" + "=" * 80)
print("条件三-B：初筛池中并购 / 重组 / 套现类公告疑点清单（近 3 年，需人工复核）")
print("=" * 80)

all_hits = []
for _, row in initial_pool.iterrows():
    hits = scan_bad_announcements(row["代码"], row["名称"])
    all_hits.extend(hits)

if all_hits:
    hits_df = pd.DataFrame(all_hits)
    print(hits_df.to_string(index=False))
    # hits_df.to_excel("初筛池_并购重组套现公告疑点.xlsx", index=False)
else:
    print("未扫描到命中关键词的公告（注意：关键词覆盖有限，不排除遗漏）。")


# ---------- 5. 最终输出结构 ----------
print("\n" + "=" * 80)
print("最终结果使用说明")
print("=" * 80)
print("""
1. 上方“大额减持股东清单”中列出的每一只股票、每一个股东名称，需要人工判断：
   - 该股东是否为招股说明书中的原始股东 / 控股股东 / 实际控制人及其关联方；
   - 该笔减持是否属于“大额套现”。
   如确认为原始股东大额减持，则该股票不满足条件三，应从最终名单中剔除。

2. 上方“并购/重组/套现公告疑点清单”中的每一条，需要人工打开公告原文确认：
   - 是否构成重大资产重组 / 借壳 / 卖壳；
   - 是否涉及控股股东或实控人的大额套现安排。
   如确认命中，则剔除。

3. 经上述两步人工复核后，剩余的股票才是同时满足三项条件的最终结果。

4. 分红融资比的代理指标口径提醒：
   “累计股息(%) / 融资总额(亿)” 是相对强度代理指标，不是“累计分红金额 / 累计融资金额”的
   绝对金额比。如需严格口径，请用 Tushare dividend 接口或问财导出数据替换初筛步骤。
""")
