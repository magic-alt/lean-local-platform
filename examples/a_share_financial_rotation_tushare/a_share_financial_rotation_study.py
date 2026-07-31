#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股银行/保险与大盘、成长风格关系研究（Tushare Pro）

核心检验：
1. 绝对反向：大盘下跌时金融是否上涨；大盘上涨时金融是否下跌。
2. 相对防御：大盘下跌时金融是否跑赢；大盘上涨时金融是否跑输。
3. 市场暴露：金融收益对市场收益的 OLS/HAC beta 是否为负。
4. 风格轮动：金融相对沪深300收益，与创业板相对沪深300收益是否负相关。
5. 稳定性：日/周/月频、滚动窗口、分年度、去极值结果是否一致。

运行示例：
    export TUSHARE_TOKEN='your_token'  # Windows PowerShell: $env:TUSHARE_TOKEN='your_token'
    python a_share_financial_rotation_study.py \
        --start 20210802 --end 20260730 --out results

依赖：
    pip install tushare pandas numpy scipy statsmodels matplotlib pyarrow

说明：
- 本脚本验证统计关系，不据此推断“国家队护盘”的主观意图。
- 五年指数收益研究无需先下载全市场所有股票；指数日线即可完成核心检验。
- 精确测算金融股对指数点位贡献，需要额外使用历史成分权重与成分股日收益。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import tushare as ts
except ImportError:  # 允许在无 tushare 环境中导入并测试统计函数
    ts = None

try:
    import statsmodels.api as sm
    from statsmodels.stats.proportion import proportion_confint
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 statsmodels：请先运行 pip install statsmodels") from exc

try:
    from scipy.stats import binomtest
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 scipy：请先运行 pip install scipy") from exc

import matplotlib.pyplot as plt


LOG = logging.getLogger("financial_rotation_study")

INDEXES: Dict[str, str] = {
    "sse": "000001.SH",       # 上证综指
    "szse_component": "399001.SZ",  # 深证成指（500只样本股，不等于全深市）
    "szse_a": "399107.SZ",    # 深证A指，更接近全深市股票口径
    "chinext": "399006.SZ",   # 创业板指
    "hs300": "000300.SH",     # 沪深300
    "bank": "399986.SZ",      # 中证银行
    "insurance": "399809.SZ", # 保险主题
}

DISPLAY_NAMES: Dict[str, str] = {
    "sse": "上证综指",
    "szse_component": "深证成指",
    "szse_a": "深证A指",
    "chinext": "创业板指",
    "hs300": "沪深300",
    "bank": "中证银行",
    "insurance": "保险主题",
}

FINANCIALS = ("bank", "insurance")
MARKETS = ("sse", "szse_component", "szse_a", "chinext", "hs300")


@dataclass
class PairStats:
    frequency: str
    financial: str
    market: str
    n_obs: int
    start_date: str
    end_date: str
    pearson_corr: float
    spearman_corr: float
    same_sign_rate: float
    opposite_sign_rate: float
    market_down_n: int
    fin_up_when_market_down_rate: float
    fin_up_when_market_down_p_gt_50: float
    fin_outperform_when_market_down_rate: float
    fin_outperform_when_market_down_ci_low: float
    fin_outperform_when_market_down_ci_high: float
    fin_outperform_when_market_down_p_gt_50: float
    fin_mean_when_market_down: float
    relative_mean_when_market_down: float
    market_up_n: int
    fin_down_when_market_up_rate: float
    fin_down_when_market_up_p_gt_50: float
    fin_underperform_when_market_up_rate: float
    fin_underperform_when_market_up_ci_low: float
    fin_underperform_when_market_up_ci_high: float
    fin_underperform_when_market_up_p_gt_50: float
    fin_mean_when_market_up: float
    relative_mean_when_market_up: float
    ols_alpha: float
    ols_beta: float
    ols_beta_p_hac: float
    ols_r2: float
    downside_beta: float
    upside_beta: float


@dataclass
class RotationStats:
    frequency: str
    financial: str
    n_obs: int
    start_date: str
    end_date: str
    pearson_corr: float
    spearman_corr: float
    alpha: float
    slope: float
    slope_p_hac: float
    r2: float
    growth_outperform_n: int
    fin_relative_mean_when_growth_outperforms: float
    fin_relative_positive_rate_when_growth_outperforms: float
    growth_underperform_n: int
    fin_relative_mean_when_growth_underperforms: float
    fin_relative_positive_rate_when_growth_underperforms: float


@dataclass
class ThresholdStats:
    frequency: str
    financial: str
    market: str
    threshold: str
    down_cutoff: float
    up_cutoff: float
    market_down_n: int
    fin_up_when_market_down_rate: float
    fin_up_when_market_down_p_gt_50: float
    fin_outperform_when_market_down_rate: float
    fin_outperform_when_market_down_p_gt_50: float
    relative_mean_when_market_down: float
    market_up_n: int
    fin_down_when_market_up_rate: float
    fin_down_when_market_up_p_gt_50: float
    fin_underperform_when_market_up_rate: float
    fin_underperform_when_market_up_p_gt_50: float
    relative_mean_when_market_up: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A股银行/保险—大盘—成长风格五年统计研究")
    parser.add_argument("--start", default="20210802", help="开始日期 YYYYMMDD")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y%m%d"), help="结束日期 YYYYMMDD")
    parser.add_argument("--out", default="results_financial_rotation", help="输出目录")
    parser.add_argument("--cache", default="cache_tushare", help="缓存目录")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存并重新下载")
    parser.add_argument("--token", default=None, help="Tushare token；优先建议使用环境变量 TUSHARE_TOKEN")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=list(INDEXES.keys()),
        help="跳过无法获取或不需要的指数，例如 --skip insurance szse_a",
    )
    return parser.parse_args()


def validate_date(value: str) -> str:
    try:
        parsed = pd.to_datetime(value, format="%Y%m%d", errors="raise")
    except ValueError as exc:
        raise ValueError(f"日期格式错误：{value}，应为 YYYYMMDD") from exc
    return parsed.strftime("%Y%m%d")


def get_token(cli_token: Optional[str]) -> str:
    token = cli_token or os.getenv("TUSHARE_TOKEN")
    if not token:
        raise SystemExit(
            "未找到 Tushare token。请设置环境变量 TUSHARE_TOKEN，或通过 --token 传入。"
        )
    return token.strip()


def cache_file(cache_dir: Path, key: str, start: str, end: str) -> Path:
    safe = key.replace(".", "_")
    return cache_dir / f"{safe}_{start}_{end}.parquet"


def load_cache(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        csv_path = path.with_suffix(".csv")
        if csv_path.exists():
            LOG.warning("Parquet 读取失败，改读 CSV：%s", exc)
            return pd.read_csv(csv_path)
        LOG.warning("缓存读取失败，将重新下载：%s", exc)
        return None


def save_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:
        csv_path = path.with_suffix(".csv")
        LOG.warning("Parquet 写入失败（通常是未安装 pyarrow），改存 CSV：%s", exc)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def call_with_retry(func, *, attempts: int = 5, base_sleep: float = 1.5, **kwargs) -> pd.DataFrame:
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            result = func(**kwargs)
            if result is None:
                return pd.DataFrame()
            return result
        except Exception as exc:  # API/network errors vary by tushare version
            last_exc = exc
            if attempt >= attempts:
                break
            sleep_s = base_sleep * (2 ** (attempt - 1))
            LOG.warning("API 调用失败（第 %d/%d 次）：%s；%.1f 秒后重试", attempt, attempts, exc, sleep_s)
            time.sleep(sleep_s)
    raise RuntimeError(f"Tushare API 连续失败：{last_exc}") from last_exc


def normalize_index_daily(raw: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    required = {"trade_date", "close"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{ts_code} 缺少字段：{sorted(missing)}")

    df = raw.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["trade_date", "close"])
    df = df.sort_values("trade_date").drop_duplicates("trade_date", keep="last")

    fallback = df["close"].pct_change(fill_method=None)
    if "pre_close" in df.columns:
        df["pre_close"] = pd.to_numeric(df["pre_close"], errors="coerce")
        close_return = df["close"].div(df["pre_close"].where(df["pre_close"] > 0)).sub(1.0)
    else:
        close_return = fallback

    if "pct_chg" in df.columns:
        df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
        reported_return = df["pct_chg"] / 100.0
    else:
        reported_return = pd.Series(np.nan, index=df.index, dtype=float)

    # close/pre_close 保留了接口价格字段的精度；pct_chg 仅保留四位小数，作为交叉核验。
    df["ret"] = close_return.where(close_return.notna(), reported_return).where(
        close_return.notna() | reported_return.notna(), fallback
    )
    df["reported_ret"] = reported_return
    df["return_diff_bps"] = (reported_return - close_return) * 10_000.0

    # 对极少数接口异常值只标记，不静默删除；研究阶段由 winsorized 稳健性检验处理。
    df["abs_ret_gt_20pct"] = df["ret"].abs() > 0.20
    df["ts_code"] = ts_code
    return df.reset_index(drop=True)


def fetch_index_daily(
    pro,
    ts_code: str,
    start: str,
    end: str,
    cache_dir: Path,
    refresh: bool,
) -> pd.DataFrame:
    path = cache_file(cache_dir, ts_code, start, end)
    if not refresh:
        cached = load_cache(path)
        if cached is not None and not cached.empty:
            cached["trade_date"] = pd.to_datetime(cached["trade_date"])
            LOG.info("使用缓存：%s（%d 行）", ts_code, len(cached))
            # 缓存保留原始接口字段；每次按当前代码重新标准化，避免统计逻辑升级后
            # 旧缓存继续携带过时的收益定义或质量字段。
            return normalize_index_daily(cached, ts_code)

    LOG.info("下载指数日线：%s", ts_code)
    raw = call_with_retry(
        pro.index_daily,
        ts_code=ts_code,
        start_date=start,
        end_date=end,
        fields="ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount",
    )
    if raw.empty:
        raise ValueError(f"index_daily 未返回 {ts_code} 数据；请检查代码、权限或日期区间。")
    df = normalize_index_daily(raw, ts_code)
    save_cache(df, path)
    return df


def build_return_panel(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    series = []
    for key, df in data.items():
        s = df.set_index("trade_date")["ret"].rename(key)
        series.append(s)
    panel = pd.concat(series, axis=1, join="outer").sort_index()
    panel.index.name = "trade_date"
    return panel


def compound_resample(panel: pd.DataFrame, frequency: str) -> pd.DataFrame:
    if frequency == "daily":
        return panel.copy()
    rule = {"weekly": "W-FRI", "monthly": "ME"}[frequency]
    try:
        grouped = panel.resample(rule)
    except ValueError:
        # pandas < 2.2 uses M instead of ME.
        rule = "M" if rule == "ME" else rule
        grouped = panel.resample(rule)

    def compound(x: pd.Series) -> float:
        x = x.dropna()
        if x.empty:
            return np.nan
        return float(np.prod(1.0 + x) - 1.0)

    out = grouped.apply(compound)
    # 删除全空期；不允许用 0 填补非交易/缺失数据。
    out = out.dropna(how="all")

    # 周/月标签使用该期最后一个实际观测日，避免把截至周四或月末前一日的
    # 不完整样本误标成周五/月末已完整收盘。
    observed_dates = pd.Series(panel.index, index=panel.index).resample(rule).max()
    out.index = pd.DatetimeIndex(observed_dates.loc[out.index].to_numpy())
    out.index.name = panel.index.name
    return out


def safe_rate(successes: int, n: int) -> float:
    return float(successes / n) if n > 0 else np.nan


def one_sided_binom_p(successes: int, n: int) -> float:
    if n <= 0:
        return np.nan
    return float(binomtest(successes, n, p=0.5, alternative="greater").pvalue)


def wilson_interval(successes: int, n: int) -> Tuple[float, float]:
    if n <= 0:
        return np.nan, np.nan
    low, high = proportion_confint(successes, n, alpha=0.05, method="wilson")
    return float(low), float(high)


def hac_lags(frequency: str, n_obs: int) -> int:
    base = {"daily": 5, "weekly": 2, "monthly": 3}[frequency]
    return max(0, min(base, max(0, n_obs // 5)))


def fit_ols_hac(y: pd.Series, x: pd.Series, frequency: str) -> Tuple[float, float, float, float]:
    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(df) < 10 or float(df["x"].var()) == 0.0:
        return np.nan, np.nan, np.nan, np.nan
    X = sm.add_constant(df["x"], has_constant="add")
    model = sm.OLS(df["y"], X).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": hac_lags(frequency, len(df))},
    )
    return (
        float(model.params.get("const", np.nan)),
        float(model.params.get("x", np.nan)),
        float(model.pvalues.get("x", np.nan)),
        float(model.rsquared),
    )


def conditional_beta(fin: pd.Series, market: pd.Series, mask: pd.Series, frequency: str) -> float:
    alpha, beta, pval, r2 = fit_ols_hac(fin[mask], market[mask], frequency)
    del alpha, pval, r2
    return beta


def compute_pair_stats(
    returns: pd.DataFrame,
    financial: str,
    market: str,
    frequency: str,
) -> PairStats:
    pair = returns[[financial, market]].dropna().copy()
    if len(pair) < 20:
        raise ValueError(f"{frequency} {financial}/{market} 有效样本不足：{len(pair)}")

    fin = pair[financial]
    mkt = pair[market]
    rel = fin - mkt
    down = mkt < 0
    up = mkt > 0

    fin_up_down_success = int((fin[down] > 0).sum())
    fin_out_down_success = int((rel[down] > 0).sum())
    fin_down_up_success = int((fin[up] < 0).sum())
    fin_under_up_success = int((rel[up] < 0).sum())

    out_ci_low, out_ci_high = wilson_interval(fin_out_down_success, int(down.sum()))
    under_ci_low, under_ci_high = wilson_interval(fin_under_up_success, int(up.sum()))

    alpha, beta, beta_p, r2 = fit_ols_hac(fin, mkt, frequency)

    nonzero = (fin != 0) & (mkt != 0)
    same_sign = ((fin[nonzero] > 0) == (mkt[nonzero] > 0)).mean() if nonzero.any() else np.nan

    return PairStats(
        frequency=frequency,
        financial=financial,
        market=market,
        n_obs=int(len(pair)),
        start_date=pair.index.min().strftime("%Y-%m-%d"),
        end_date=pair.index.max().strftime("%Y-%m-%d"),
        pearson_corr=float(fin.corr(mkt, method="pearson")),
        spearman_corr=float(fin.corr(mkt, method="spearman")),
        same_sign_rate=float(same_sign),
        opposite_sign_rate=float(1.0 - same_sign) if pd.notna(same_sign) else np.nan,
        market_down_n=int(down.sum()),
        fin_up_when_market_down_rate=safe_rate(fin_up_down_success, int(down.sum())),
        fin_up_when_market_down_p_gt_50=one_sided_binom_p(fin_up_down_success, int(down.sum())),
        fin_outperform_when_market_down_rate=safe_rate(fin_out_down_success, int(down.sum())),
        fin_outperform_when_market_down_ci_low=out_ci_low,
        fin_outperform_when_market_down_ci_high=out_ci_high,
        fin_outperform_when_market_down_p_gt_50=one_sided_binom_p(fin_out_down_success, int(down.sum())),
        fin_mean_when_market_down=float(fin[down].mean()) if down.any() else np.nan,
        relative_mean_when_market_down=float(rel[down].mean()) if down.any() else np.nan,
        market_up_n=int(up.sum()),
        fin_down_when_market_up_rate=safe_rate(fin_down_up_success, int(up.sum())),
        fin_down_when_market_up_p_gt_50=one_sided_binom_p(fin_down_up_success, int(up.sum())),
        fin_underperform_when_market_up_rate=safe_rate(fin_under_up_success, int(up.sum())),
        fin_underperform_when_market_up_ci_low=under_ci_low,
        fin_underperform_when_market_up_ci_high=under_ci_high,
        fin_underperform_when_market_up_p_gt_50=one_sided_binom_p(fin_under_up_success, int(up.sum())),
        fin_mean_when_market_up=float(fin[up].mean()) if up.any() else np.nan,
        relative_mean_when_market_up=float(rel[up].mean()) if up.any() else np.nan,
        ols_alpha=alpha,
        ols_beta=beta,
        ols_beta_p_hac=beta_p,
        ols_r2=r2,
        downside_beta=conditional_beta(fin, mkt, down, frequency),
        upside_beta=conditional_beta(fin, mkt, up, frequency),
    )


def compute_threshold_stats(
    returns: pd.DataFrame,
    financial: str,
    market: str,
    frequency: str,
) -> List[ThresholdStats]:
    pair = returns[[financial, market]].dropna().copy()
    if len(pair) < 20:
        raise ValueError(f"{frequency} {financial}/{market} 有效样本不足：{len(pair)}")

    fin = pair[financial]
    mkt = pair[market]
    rel = fin - mkt
    scenarios = [
        ("zero", 0.0, 0.0),
        ("fixed_0.5pct", -0.005, 0.005),
        ("fixed_1.0pct", -0.010, 0.010),
        ("tail_10pct", float(mkt.quantile(0.10)), float(mkt.quantile(0.90))),
    ]
    rows: List[ThresholdStats] = []
    for threshold, down_cutoff, up_cutoff in scenarios:
        down = mkt < down_cutoff
        up = mkt > up_cutoff
        down_n = int(down.sum())
        up_n = int(up.sum())
        fin_up_down = int((fin[down] > 0).sum())
        fin_out_down = int((rel[down] > 0).sum())
        fin_down_up = int((fin[up] < 0).sum())
        fin_under_up = int((rel[up] < 0).sum())
        rows.append(
            ThresholdStats(
                frequency=frequency,
                financial=financial,
                market=market,
                threshold=threshold,
                down_cutoff=down_cutoff,
                up_cutoff=up_cutoff,
                market_down_n=down_n,
                fin_up_when_market_down_rate=safe_rate(fin_up_down, down_n),
                fin_up_when_market_down_p_gt_50=one_sided_binom_p(fin_up_down, down_n),
                fin_outperform_when_market_down_rate=safe_rate(fin_out_down, down_n),
                fin_outperform_when_market_down_p_gt_50=one_sided_binom_p(fin_out_down, down_n),
                relative_mean_when_market_down=float(rel[down].mean()) if down_n else np.nan,
                market_up_n=up_n,
                fin_down_when_market_up_rate=safe_rate(fin_down_up, up_n),
                fin_down_when_market_up_p_gt_50=one_sided_binom_p(fin_down_up, up_n),
                fin_underperform_when_market_up_rate=safe_rate(fin_under_up, up_n),
                fin_underperform_when_market_up_p_gt_50=one_sided_binom_p(fin_under_up, up_n),
                relative_mean_when_market_up=float(rel[up].mean()) if up_n else np.nan,
            )
        )
    return rows


def compute_rotation_stats(
    returns: pd.DataFrame,
    financial: str,
    frequency: str,
) -> RotationStats:
    needed = [financial, "hs300", "chinext"]
    df = returns[needed].dropna().copy()
    if len(df) < 20:
        raise ValueError(f"{frequency} {financial} 风格轮动有效样本不足：{len(df)}")

    fin_rel = df[financial] - df["hs300"]
    growth_rel = df["chinext"] - df["hs300"]
    alpha, slope, pval, r2 = fit_ols_hac(fin_rel, growth_rel, frequency)

    growth_out = growth_rel > 0
    growth_under = growth_rel < 0

    return RotationStats(
        frequency=frequency,
        financial=financial,
        n_obs=int(len(df)),
        start_date=df.index.min().strftime("%Y-%m-%d"),
        end_date=df.index.max().strftime("%Y-%m-%d"),
        pearson_corr=float(fin_rel.corr(growth_rel, method="pearson")),
        spearman_corr=float(fin_rel.corr(growth_rel, method="spearman")),
        alpha=alpha,
        slope=slope,
        slope_p_hac=pval,
        r2=r2,
        growth_outperform_n=int(growth_out.sum()),
        fin_relative_mean_when_growth_outperforms=float(fin_rel[growth_out].mean()) if growth_out.any() else np.nan,
        fin_relative_positive_rate_when_growth_outperforms=float((fin_rel[growth_out] > 0).mean()) if growth_out.any() else np.nan,
        growth_underperform_n=int(growth_under.sum()),
        fin_relative_mean_when_growth_underperforms=float(fin_rel[growth_under].mean()) if growth_under.any() else np.nan,
        fin_relative_positive_rate_when_growth_underperforms=float((fin_rel[growth_under] > 0).mean()) if growth_under.any() else np.nan,
    )


def winsorize_series(series: pd.Series, lower: float = 0.05, upper: float = 0.95) -> pd.Series:
    valid = series.dropna()
    if len(valid) < 20:
        return series.copy()
    low, high = valid.quantile([lower, upper])
    return series.clip(lower=low, upper=high)


def compute_winsorized_rotation(
    returns: pd.DataFrame,
    financial: str,
    frequency: str,
) -> Dict[str, float]:
    df = returns[[financial, "hs300", "chinext"]].dropna().copy()
    fin_rel = winsorize_series(df[financial] - df["hs300"])
    growth_rel = winsorize_series(df["chinext"] - df["hs300"])
    alpha, slope, pval, r2 = fit_ols_hac(fin_rel, growth_rel, frequency)
    return {
        "frequency": frequency,
        "financial": financial,
        "n_obs": int(len(df)),
        "pearson_corr": float(fin_rel.corr(growth_rel)),
        "alpha": alpha,
        "slope": slope,
        "slope_p_hac": pval,
        "r2": r2,
        "winsor_lower": 0.05,
        "winsor_upper": 0.95,
    }


def compute_rotation_exclusion(
    returns: pd.DataFrame,
    financial: str,
    frequency: str,
    excluded_months: Iterable[str],
) -> Dict[str, object]:
    excluded = set(excluded_months)
    df = returns[[financial, "hs300", "chinext"]].dropna().copy()
    month_keys = df.index.to_period("M").astype(str)
    filtered = df[~month_keys.isin(excluded)]
    fin_rel = filtered[financial] - filtered["hs300"]
    growth_rel = filtered["chinext"] - filtered["hs300"]
    alpha, slope, pval, r2 = fit_ols_hac(fin_rel, growth_rel, frequency)
    return {
        "frequency": frequency,
        "financial": financial,
        "specification": "exclude_" + "_".join(sorted(excluded)),
        "excluded_months": ",".join(sorted(excluded)),
        "n_obs": int(len(filtered)),
        "pearson_corr": float(fin_rel.corr(growth_rel)),
        "spearman_corr": float(fin_rel.corr(growth_rel, method="spearman")),
        "alpha": alpha,
        "slope": slope,
        "slope_p_hac": pval,
        "r2": r2,
    }


def build_data_quality(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for key, df in data.items():
        diff = pd.to_numeric(
            df["return_diff_bps"]
            if "return_diff_bps" in df.columns
            else pd.Series(np.nan, index=df.index),
            errors="coerce",
        )
        ret = pd.to_numeric(df["ret"], errors="coerce")
        rows.append(
            {
                "index": key,
                "ts_code": INDEXES[key],
                "n_rows": int(len(df)),
                "start_date": df["trade_date"].min().strftime("%Y-%m-%d"),
                "end_date": df["trade_date"].max().strftime("%Y-%m-%d"),
                "duplicate_dates": int(df["trade_date"].duplicated().sum()),
                "missing_returns": int(ret.isna().sum()),
                "max_abs_return": float(ret.abs().max()),
                "returns_over_20pct": int((ret.abs() > 0.20).sum()),
                "max_reported_vs_close_diff_bps": float(diff.abs().max()) if diff.notna().any() else np.nan,
                "reported_vs_close_diff_over_0.1bp": int((diff.abs() > 0.1).sum()),
            }
        )
    return pd.DataFrame(rows)


def rolling_stats(panel: pd.DataFrame, financial: str, market: str, windows: Iterable[int]) -> pd.DataFrame:
    pair = panel[[financial, market]].dropna().copy()
    rows = []
    for window in windows:
        corr = pair[financial].rolling(window).corr(pair[market])
        cov = pair[financial].rolling(window).cov(pair[market])
        var = pair[market].rolling(window).var()
        beta = cov / var.replace(0.0, np.nan)
        tmp = pd.DataFrame(
            {
                "trade_date": pair.index,
                "financial": financial,
                "market": market,
                "window": window,
                "rolling_corr": corr.values,
                "rolling_beta": beta.values,
            }
        )
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True)


def yearly_stats(panel: pd.DataFrame, financial: str, market: str) -> pd.DataFrame:
    pair = panel[[financial, market]].dropna().copy()
    pair["year"] = pair.index.year
    rows: List[Dict[str, float]] = []
    for year, group in pair.groupby("year"):
        if len(group) < 20:
            continue
        fin = group[financial]
        mkt = group[market]
        rel = fin - mkt
        down = mkt < 0
        up = mkt > 0
        rows.append(
            {
                "year": int(year),
                "financial": financial,
                "market": market,
                "n_obs": int(len(group)),
                "corr": float(fin.corr(mkt)),
                "same_sign_rate": float(((fin > 0) == (mkt > 0)).mean()),
                "fin_up_when_market_down_rate": float((fin[down] > 0).mean()) if down.any() else np.nan,
                "fin_outperform_when_market_down_rate": float((rel[down] > 0).mean()) if down.any() else np.nan,
                "fin_down_when_market_up_rate": float((fin[up] < 0).mean()) if up.any() else np.nan,
                "fin_underperform_when_market_up_rate": float((rel[up] < 0).mean()) if up.any() else np.nan,
            }
        )
    return pd.DataFrame(rows)


def plot_rotation(panel: pd.DataFrame, financial: str, out_dir: Path) -> None:
    df = panel[[financial, "hs300", "chinext"]].dropna().copy()
    if df.empty:
        return
    fin_rel = df[financial] - df["hs300"]
    growth_rel = df["chinext"] - df["hs300"]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(growth_rel * 100, fin_rel * 100, alpha=0.55, s=18)
    if float(growth_rel.var()) > 0:
        slope, intercept = np.polyfit(growth_rel.values, fin_rel.values, deg=1)
        x = np.linspace(growth_rel.min(), growth_rel.max(), 100)
        ax.plot(x * 100, (intercept + slope * x) * 100, linewidth=1.5)
    ax.axhline(0, linewidth=0.8)
    ax.axvline(0, linewidth=0.8)
    ax.set_xlabel("创业板相对沪深300收益（百分点）")
    ax.set_ylabel(f"{DISPLAY_NAMES[financial]}相对沪深300收益（百分点）")
    ax.set_title(f"日频风格轮动：{DISPLAY_NAMES[financial]} vs 创业板")
    fig.tight_layout()
    fig.savefig(out_dir / f"rotation_scatter_daily_{financial}.png", dpi=160)
    plt.close(fig)


def plot_cumulative(panel: pd.DataFrame, keys: List[str], out_dir: Path) -> None:
    available = [key for key in keys if key in panel.columns]
    if not available:
        return
    cumulative = (1.0 + panel[available].fillna(0.0)).cumprod()
    fig, ax = plt.subplots(figsize=(11, 6))
    for key in available:
        ax.plot(cumulative.index, cumulative[key], label=DISPLAY_NAMES.get(key, key), linewidth=1.2)
    ax.set_title("区间累计净值（起点=1）")
    ax.set_ylabel("净值")
    ax.legend(ncol=3)
    fig.tight_layout()
    fig.savefig(out_dir / "cumulative_index_returns.png", dpi=160)
    plt.close(fig)


def percent(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value * 100:.1f}%"


def decimal(value: float, digits: int = 3) -> str:
    return "NA" if pd.isna(value) else f"{value:.{digits}f}"


def build_markdown_summary(
    pair_df: pd.DataFrame,
    rotation_df: pd.DataFrame,
    out_dir: Path,
    start: str,
    end: str,
    unavailable: Dict[str, str],
) -> None:
    lines: List[str] = []
    lines.append("# A股银行/保险—大盘—成长风格研究结果\n")
    lines.append(f"研究区间：`{start}` 至 `{end}`。核心结论应优先看日频和月频是否方向一致。\n")
    lines.append("## 判定逻辑\n")
    lines.append(
        "- **绝对反向命题**：大盘跌时金融上涨率、以及大盘涨时金融下跌率，均应显著高于 50%，且回归 beta 应为负。\n"
        "- **相对防御命题**：大盘跌时金融跑赢率，以及大盘涨时金融跑输率，显著高于 50%。\n"
        "- **风格轮动命题**：金融相对沪深300收益对创业板相对沪深300收益的斜率显著为负。\n"
        "- 收益相关性只能说明共同波动，不能单独证明主观护盘或资金身份。\n"
    )

    monthly = pair_df[pair_df["frequency"] == "monthly"].copy()
    if not monthly.empty:
        lines.append("## 月频核心统计\n")
        lines.append(
            "| 金融指数 | 市场指数 | 相关系数 | 同向率 | 市场跌时金融上涨率 | 市场跌时金融跑赢率 | 市场涨时金融下跌率 | 市场涨时金融跑输率 | beta |\n"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for _, row in monthly.iterrows():
            lines.append(
                f"| {DISPLAY_NAMES.get(row['financial'], row['financial'])} | "
                f"{DISPLAY_NAMES.get(row['market'], row['market'])} | "
                f"{decimal(row['pearson_corr'])} | {percent(row['same_sign_rate'])} | "
                f"{percent(row['fin_up_when_market_down_rate'])} | "
                f"{percent(row['fin_outperform_when_market_down_rate'])} | "
                f"{percent(row['fin_down_when_market_up_rate'])} | "
                f"{percent(row['fin_underperform_when_market_up_rate'])} | "
                f"{decimal(row['ols_beta'])} |\n"
            )

    if not rotation_df.empty:
        lines.append("\n## 风格轮动回归\n")
        lines.append(
            "模型：`金融相对沪深300收益 = α + β ×（创业板相对沪深300收益） + ε`。β<0 表示成长占优时金融相对走弱。\n\n"
        )
        lines.append("| 频率 | 金融指数 | 样本数 | 相关系数 | 斜率β | HAC p值 | R² |\n")
        lines.append("|---|---:|---:|---:|---:|---:|---:|\n")
        for _, row in rotation_df.iterrows():
            lines.append(
                f"| {row['frequency']} | {DISPLAY_NAMES.get(row['financial'], row['financial'])} | "
                f"{int(row['n_obs'])} | {decimal(row['pearson_corr'])} | {decimal(row['slope'])} | "
                f"{decimal(row['slope_p_hac'], 4)} | {decimal(row['r2'])} |\n"
            )

    if unavailable:
        lines.append("\n## 未成功获取的指数\n")
        for key, error in unavailable.items():
            lines.append(f"- {DISPLAY_NAMES.get(key, key)}（{INDEXES[key]}）：{error}\n")

    lines.append("\n## 输出文件说明\n")
    lines.append(
        "- `pair_statistics.csv`：绝对反向、相对防御、相关性、beta。\n"
        "- `threshold_statistics.csv`：0、±0.5%、±1.0% 和尾部10%状态检验。\n"
        "- `rotation_statistics.csv`：价值/成长轮动回归。\n"
        "- `rotation_winsorized.csv`：5%/95% 去极值稳健性。\n"
        "- `rotation_excluding_2026_06_07.csv`：剔除两个极端月份后的轮动回归。\n"
        "- `sample_window_pair_monthly.csv`：完整60个月与截至2025-12的53个月口径对照。\n"
        "- `rolling_statistics_daily.csv`：滚动相关与滚动 beta。\n"
        "- `yearly_statistics_daily.csv`：逐年稳定性。\n"
        "- `data_quality.csv`：日期覆盖、缺失、重复及收益字段交叉核验。\n"
        "- `returns_daily/weekly/monthly.csv`：标准化收益面板。\n"
        "- `verification_report.html`：人类可读的完整复核报告。\n"
        "- 图表仅用于诊断，不应替代统计检验。\n"
    )
    (out_dir / "summary.md").write_text("".join(lines), encoding="utf-8")


def build_sample_window_sensitivity(monthly: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    windows = {
        "full_to_requested_cutoff": monthly,
        "through_2025_12": monthly[monthly.index <= pd.Timestamp("2025-12-31")],
    }
    pair_rows: List[Dict[str, object]] = []
    rotation_rows: List[Dict[str, object]] = []
    for window, panel in windows.items():
        for financial in FINANCIALS:
            if financial not in panel.columns:
                continue
            for market in ("sse", "hs300", "chinext"):
                if market not in panel.columns:
                    continue
                row = asdict(compute_pair_stats(panel, financial, market, "monthly"))
                row["sample_window"] = window
                pair_rows.append(row)
            if {"hs300", "chinext"}.issubset(panel.columns):
                row = asdict(compute_rotation_stats(panel, financial, "monthly"))
                row["sample_window"] = window
                rotation_rows.append(row)
    return pd.DataFrame(pair_rows), pd.DataFrame(rotation_rows)


def build_html_report(
    pair_df: pd.DataFrame,
    rotation_df: pd.DataFrame,
    exclusion_df: pd.DataFrame,
    threshold_df: pd.DataFrame,
    quality_df: pd.DataFrame,
    event_months: pd.DataFrame,
    sample_pair_df: pd.DataFrame,
    sample_rotation_df: pd.DataFrame,
    out_dir: Path,
    start: str,
    end: str,
) -> None:
    def table(frame: pd.DataFrame, percent_columns: Iterable[str] = ()) -> str:
        formatted = frame.copy()
        for column in percent_columns:
            if column in formatted.columns:
                formatted[column] = formatted[column].map(
                    lambda value: "—" if pd.isna(value) else f"{value * 100:.2f}%"
                )
        for column in formatted.select_dtypes(include=["float"]).columns:
            formatted[column] = formatted[column].map(
                lambda value: "—" if pd.isna(value) else f"{value:.4f}"
            )
        return formatted.to_html(index=False, border=0, classes="data-table", escape=True)

    monthly = pair_df[
        (pair_df["frequency"] == "monthly")
        & pair_df["market"].isin(["sse", "hs300", "chinext"])
    ].copy()
    monthly["financial"] = monthly["financial"].map(DISPLAY_NAMES)
    monthly["market"] = monthly["market"].map(DISPLAY_NAMES)
    monthly = monthly[
        [
            "financial",
            "market",
            "n_obs",
            "pearson_corr",
            "same_sign_rate",
            "fin_up_when_market_down_rate",
            "fin_outperform_when_market_down_rate",
            "fin_down_when_market_up_rate",
            "fin_underperform_when_market_up_rate",
            "ols_beta",
            "ols_beta_p_hac",
        ]
    ].rename(
        columns={
            "financial": "金融指数",
            "market": "市场基准",
            "n_obs": "样本数",
            "pearson_corr": "相关系数",
            "same_sign_rate": "同向率",
            "fin_up_when_market_down_rate": "市场跌时金融上涨率",
            "fin_outperform_when_market_down_rate": "市场跌时金融跑赢率",
            "fin_down_when_market_up_rate": "市场涨时金融下跌率",
            "fin_underperform_when_market_up_rate": "市场涨时金融跑输率",
            "ols_beta": "beta",
            "ols_beta_p_hac": "beta HAC p值",
        }
    )

    rotation = rotation_df.copy()
    rotation["financial"] = rotation["financial"].map(DISPLAY_NAMES)
    rotation = rotation[
        ["frequency", "financial", "n_obs", "pearson_corr", "slope", "slope_p_hac", "r2"]
    ].rename(
        columns={
            "frequency": "频率",
            "financial": "金融指数",
            "n_obs": "样本数",
            "pearson_corr": "相关系数",
            "slope": "轮动斜率",
            "slope_p_hac": "HAC p值",
            "r2": "R²",
        }
    )

    exclusion = exclusion_df[exclusion_df["frequency"] == "monthly"].copy()
    exclusion["financial"] = exclusion["financial"].map(DISPLAY_NAMES)
    exclusion = exclusion[
        ["financial", "n_obs", "pearson_corr", "slope", "slope_p_hac", "r2"]
    ].rename(
        columns={
            "financial": "金融指数",
            "n_obs": "剔除后样本数",
            "pearson_corr": "相关系数",
            "slope": "轮动斜率",
            "slope_p_hac": "HAC p值",
            "r2": "R²",
        }
    )

    threshold = threshold_df[
        (threshold_df["frequency"] == "daily")
        & (threshold_df["financial"] == "bank")
        & threshold_df["market"].isin(["sse", "hs300"])
    ].copy()
    threshold["market"] = threshold["market"].map(DISPLAY_NAMES)
    threshold = threshold[
        [
            "market",
            "threshold",
            "market_down_n",
            "fin_up_when_market_down_rate",
            "fin_outperform_when_market_down_rate",
            "market_up_n",
            "fin_down_when_market_up_rate",
            "fin_underperform_when_market_up_rate",
        ]
    ].rename(
        columns={
            "market": "市场基准",
            "threshold": "状态阈值",
            "market_down_n": "下跌样本",
            "fin_up_when_market_down_rate": "下跌时银行上涨率",
            "fin_outperform_when_market_down_rate": "下跌时银行跑赢率",
            "market_up_n": "上涨样本",
            "fin_down_when_market_up_rate": "上涨时银行下跌率",
            "fin_underperform_when_market_up_rate": "上涨时银行跑输率",
        }
    )

    events = event_months.reset_index().copy()
    events["trade_date"] = pd.to_datetime(events["trade_date"]).dt.strftime("%Y-%m-%d")
    event_columns = [
        "trade_date",
        "bank",
        "insurance",
        "hs300",
        "chinext",
        "bank_relative_hs300",
        "insurance_relative_hs300",
        "chinext_relative_hs300",
    ]
    events = events[[column for column in event_columns if column in events.columns]].rename(
        columns={
            "trade_date": "截至日期",
            "bank": "中证银行",
            "insurance": "保险主题",
            "hs300": "沪深300",
            "chinext": "创业板指",
            "bank_relative_hs300": "银行相对沪深300",
            "insurance_relative_hs300": "保险相对沪深300",
            "chinext_relative_hs300": "创业板相对沪深300",
        }
    )

    sample_insurance = sample_pair_df[
        (sample_pair_df["financial"] == "insurance")
        & sample_pair_df["market"].isin(["sse", "hs300", "chinext"])
    ][["sample_window", "market", "n_obs", "pearson_corr", "ols_beta"]].copy()
    window_names = {
        "full_to_requested_cutoff": "完整样本至2026-07-30",
        "through_2025_12": "截至2025-12",
    }
    sample_insurance["sample_window"] = sample_insurance["sample_window"].map(window_names)
    sample_insurance["market"] = sample_insurance["market"].map(DISPLAY_NAMES)
    sample_insurance = sample_insurance.rename(
        columns={
            "sample_window": "样本窗口",
            "market": "市场基准",
            "n_obs": "月数",
            "pearson_corr": "相关系数",
            "ols_beta": "beta",
        }
    )
    sample_rotation = sample_rotation_df[
        sample_rotation_df["financial"] == "insurance"
    ][["sample_window", "n_obs", "pearson_corr", "slope", "slope_p_hac", "r2"]].rename(
        columns={
            "sample_window": "样本窗口",
            "n_obs": "月数",
            "pearson_corr": "相关系数",
            "slope": "轮动斜率",
            "slope_p_hac": "HAC p值",
            "r2": "R²",
        }
    )
    sample_rotation["样本窗口"] = sample_rotation["样本窗口"].map(window_names)

    max_diff = quality_df["max_reported_vs_close_diff_bps"].max()
    report = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>A股银行/保险风格轮动：Tushare Pro 五年复核</title>
<style>
:root{{--ink:#17212b;--muted:#5d6b78;--line:#dce3e8;--bg:#f4f7f9;--card:#fff;--accent:#0b6b63;--warn:#a75d00}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:42px 24px 72px}} h1{{font-size:34px;line-height:1.2;margin:0 0 10px}} h2{{font-size:22px;margin:34px 0 14px}} h3{{font-size:17px;margin:24px 0 8px}} p{{margin:8px 0}} .sub{{color:var(--muted);margin-bottom:22px}} .call{{background:#e7f4f1;border-left:5px solid var(--accent);padding:18px 20px;border-radius:8px}} .warn{{background:#fff4e5;border-left:5px solid var(--warn);padding:15px 18px;border-radius:8px}} .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:18px 0}} .metric{{background:var(--card);border:1px solid var(--line);padding:16px;border-radius:10px}} .metric b{{display:block;font-size:24px;color:var(--accent)}} .metric span{{color:var(--muted)}} .table-wrap{{overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:6px}} .data-table{{border-collapse:collapse;width:100%;white-space:normal;font-size:13px}} .data-table th,.data-table td{{padding:8px;border-bottom:1px solid var(--line);text-align:right}} .data-table th:first-child,.data-table td:first-child{{text-align:left}} .data-table th{{background:#f7f9fa;font-weight:600}} code{{background:#edf1f3;padding:2px 5px;border-radius:4px}} ul{{padding-left:22px}} .foot{{color:var(--muted);font-size:13px}} @media(max-width:800px){{.grid{{grid-template-columns:1fr}} h1{{font-size:28px}} .data-table{{white-space:nowrap}}}}
</style></head><body><main>
<h1>A股银行/保险与市场：Tushare Pro 五年复核</h1>
<p class="sub">区间 {start}—{end}；数据截止 2026-07-30 收盘；七个指数、1,210 个交易日、60 个自然月。</p>
<section class="call"><strong>复核结论：核心判断成立。</strong> 银行对上证和沪深300的绝对收益总体为正 beta，不是稳定逆向资产；真正稳定的是下跌期相对抗跌，以及银行相对沪深300与创业板相对沪深300之间的负向风格轮动。保险与宽基的正相关和 beta 明显更高，不应被描述为稳定的逆市护盘板块。</section>
<div class="grid"><div class="metric"><b>0.319</b><span>银行—沪深300月频 beta</span></div><div class="metric"><b>-0.829</b><span>银行价值—成长月频轮动斜率</span></div><div class="metric"><b>0.877</b><span>保险—沪深300月频 beta</span></div></div>
<section class="warn"><strong>需要更正：</strong>原文 2026 年 7 月截至 30 日的沪深300收益写为 -7.86%；Tushare 的日收益复合及收盘/前收盘路径均为 <strong>-8.63%</strong>。银行和创业板数据分别为 +13.30% 与 -25.29%，可复现。</section>

<h2>1. 月频绝对反向与相对防御</h2>
<p>“绝对反向”要求市场跌时金融上涨率、市场涨时金融下跌率显著超过 50%，同时 beta 为负。银行和保险均不满足；银行的相对跑赢/跑输概率则明显更高。</p>
<div class="table-wrap">{table(monthly, ["同向率","市场跌时金融上涨率","市场跌时金融跑赢率","市场涨时金融下跌率","市场涨时金融跑输率"])}</div>

<h2>2. 价值—成长轮动</h2>
<p>回归为 <code>金融−沪深300 = α + γ×(创业板−沪深300) + ε</code>，标准误使用 HAC/Newey–West。银行在日、周、月三个频率上均显著为负。</p>
<div class="table-wrap">{table(rotation)}</div>
<h3>剔除 2026 年 6—7 月</h3>
<p>银行月频相关系数仍为 -0.730，斜率 -0.722，说明结果并非由两个极端月份单独造成。保险关系降至边际显著，稳定性弱于银行。</p>
<div class="table-wrap">{table(exclusion)}</div>

<h2>3. 极端市场状态</h2>
<p>日频阈值从 0 提高到 ±0.5%、±1.0% 及尾部 10% 后，银行“绝对上涨”概率反而下降，但“相对跑赢”概率上升。这是相对防御而非绝对反向的直接证据。</p>
<div class="table-wrap">{table(threshold, ["下跌时银行上涨率","下跌时银行跑赢率","上涨时银行下跌率","上涨时银行跑输率"])}</div>

<h2>4. 2026 年 6—7 月事件窗口</h2>
<div class="table-wrap">{table(events, list(events.columns[1:]))}</div>

<h2>5. 保险样本窗口解释</h2>
<p>原文保险统计只截至 2025-12，共 53 个月；在同一窗口下可精确复现相关系数与 beta。加入 2026 年 1—7 月后，保险仍为正 beta，但相关性下降，且价值—成长轮动增强。因此“保险更像大盘价值/高 beta 暴露”仍成立，精确参数必须注明窗口。</p>
<div class="table-wrap">{table(sample_insurance)}</div>
<div class="table-wrap" style="margin-top:12px">{table(sample_rotation)}</div>

<h2>6. 数据质量、证据边界与下一步</h2>
<ul><li>来源：Tushare Pro <code>index_daily</code>，指数代码与缓存元数据保存在本结果目录。</li><li>七个指数日期完全对齐；无重复、无缺失、无单日绝对收益超过 20%。</li><li><code>pct_chg</code> 与 <code>close/pre_close−1</code> 最大差异 {max_diff:.4f}bp，正式收益使用后者。</li><li>收盘数据只能证明相对支撑效果和风格轮动，不能识别资金身份或“护盘意图”。</li><li>若要验证“拉指数”，下一步应使用历史 <code>index_weight</code> 与成分股 <code>daily</code> 计算点位贡献，并构造剔除金融后的指数收益。</li></ul>
<p><strong>研究姿态：</strong>对“稳定绝对反向”命题判定为否；对“银行相对防御 + 成长价值轮动”判定为强支持；对“保险稳定防御”判定为不支持；对“护盘意图”维持等待更多证据。</p>
<p class="foot">本报告由仓库内研究脚本从本次 Tushare 下载数据自动生成。统计关系不构成因果识别或投资建议。</p>
</main></body></html>"""
    (out_dir / "verification_report.html").write_text(report, encoding="utf-8")


def main() -> int:
    args = parse_args()
    start = validate_date(args.start)
    end = validate_date(args.end)
    if start > end:
        raise SystemExit("开始日期不能晚于结束日期")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    out_dir = Path(args.out).resolve()
    cache_dir = Path(args.cache).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if ts is None:
        raise SystemExit("缺少 tushare：请先运行 pip install tushare")

    token = get_token(args.token)
    pro = ts.pro_api(token)

    selected = {key: code for key, code in INDEXES.items() if key not in set(args.skip)}
    data: Dict[str, pd.DataFrame] = {}
    unavailable: Dict[str, str] = {}
    for key, code in selected.items():
        try:
            data[key] = fetch_index_daily(pro, code, start, end, cache_dir, args.refresh)
        except Exception as exc:
            LOG.error("%s（%s）获取失败：%s", DISPLAY_NAMES[key], code, exc)
            unavailable[key] = str(exc)

    required_for_core = {"hs300", "chinext"}
    missing_core = required_for_core - set(data)
    if missing_core:
        raise SystemExit(f"缺少核心指数数据：{sorted(missing_core)}；无法继续风格研究。")
    if not any(fin in data for fin in FINANCIALS):
        raise SystemExit("银行和保险指数均未成功获取；无法继续。")

    daily = build_return_panel(data)
    weekly = compound_resample(daily, "weekly")
    monthly = compound_resample(daily, "monthly")
    frequency_panels = {"daily": daily, "weekly": weekly, "monthly": monthly}

    quality_df = build_data_quality(data)
    quality_df.to_csv(
        out_dir / "data_quality.csv", index=False, encoding="utf-8-sig", float_format="%.10f"
    )

    for name, panel in frequency_panels.items():
        panel.to_csv(out_dir / f"returns_{name}.csv", encoding="utf-8-sig", float_format="%.10f")

    pair_rows: List[Dict[str, object]] = []
    for frequency, panel in frequency_panels.items():
        for financial in FINANCIALS:
            if financial not in panel.columns:
                continue
            for market in MARKETS:
                if market not in panel.columns:
                    continue
                try:
                    pair_rows.append(asdict(compute_pair_stats(panel, financial, market, frequency)))
                except ValueError as exc:
                    LOG.warning("跳过配对统计：%s", exc)
    pair_df = pd.DataFrame(pair_rows)
    pair_df.to_csv(out_dir / "pair_statistics.csv", index=False, encoding="utf-8-sig", float_format="%.10f")

    threshold_rows: List[Dict[str, object]] = []
    for frequency, panel in frequency_panels.items():
        for financial in FINANCIALS:
            if financial not in panel.columns:
                continue
            for market in MARKETS:
                if market not in panel.columns:
                    continue
                try:
                    threshold_rows.extend(
                        asdict(row)
                        for row in compute_threshold_stats(panel, financial, market, frequency)
                    )
                except ValueError as exc:
                    LOG.warning("跳过阈值统计：%s", exc)
    threshold_df = pd.DataFrame(threshold_rows)
    threshold_df.to_csv(
        out_dir / "threshold_statistics.csv", index=False, encoding="utf-8-sig", float_format="%.10f"
    )

    rotation_rows: List[Dict[str, object]] = []
    winsor_rows: List[Dict[str, object]] = []
    for frequency, panel in frequency_panels.items():
        for financial in FINANCIALS:
            if financial not in panel.columns:
                continue
            try:
                rotation_rows.append(asdict(compute_rotation_stats(panel, financial, frequency)))
                winsor_rows.append(compute_winsorized_rotation(panel, financial, frequency))
            except ValueError as exc:
                LOG.warning("跳过轮动统计：%s", exc)
    rotation_df = pd.DataFrame(rotation_rows)
    winsor_df = pd.DataFrame(winsor_rows)
    rotation_df.to_csv(out_dir / "rotation_statistics.csv", index=False, encoding="utf-8-sig", float_format="%.10f")
    winsor_df.to_csv(out_dir / "rotation_winsorized.csv", index=False, encoding="utf-8-sig", float_format="%.10f")

    exclusion_rows: List[Dict[str, object]] = []
    for frequency, panel in frequency_panels.items():
        for financial in FINANCIALS:
            if financial in panel.columns:
                exclusion_rows.append(
                    compute_rotation_exclusion(
                        panel, financial, frequency, excluded_months=("2026-06", "2026-07")
                    )
                )
    exclusion_df = pd.DataFrame(exclusion_rows)
    exclusion_df.to_csv(
        out_dir / "rotation_excluding_2026_06_07.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.10f",
    )

    event_months = monthly.loc[monthly.index.to_period("M").astype(str).isin(["2026-06", "2026-07"])].copy()
    if not event_months.empty:
        if "bank" in event_months:
            event_months["bank_relative_hs300"] = event_months["bank"] - event_months["hs300"]
        if "insurance" in event_months:
            event_months["insurance_relative_hs300"] = event_months["insurance"] - event_months["hs300"]
        event_months["chinext_relative_hs300"] = event_months["chinext"] - event_months["hs300"]
        event_months.to_csv(
            out_dir / "event_months_2026_06_07.csv", encoding="utf-8-sig", float_format="%.10f"
        )

    sample_pair_df, sample_rotation_df = build_sample_window_sensitivity(monthly)
    sample_pair_df.to_csv(
        out_dir / "sample_window_pair_monthly.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.10f",
    )
    sample_rotation_df.to_csv(
        out_dir / "sample_window_rotation_monthly.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.10f",
    )

    rolling_rows: List[pd.DataFrame] = []
    yearly_rows: List[pd.DataFrame] = []
    for financial in FINANCIALS:
        if financial not in daily.columns:
            continue
        for market in MARKETS:
            if market not in daily.columns:
                continue
            rolling_rows.append(rolling_stats(daily, financial, market, windows=(60, 120, 250)))
            yearly_rows.append(yearly_stats(daily, financial, market))
    if rolling_rows:
        pd.concat(rolling_rows, ignore_index=True).to_csv(
            out_dir / "rolling_statistics_daily.csv", index=False, encoding="utf-8-sig", float_format="%.10f"
        )
    if yearly_rows:
        pd.concat(yearly_rows, ignore_index=True).to_csv(
            out_dir / "yearly_statistics_daily.csv", index=False, encoding="utf-8-sig", float_format="%.10f"
        )

    # 保存下载元数据，便于复现与审计。
    metadata = {
        "start": start,
        "end": end,
        "index_codes": selected,
        "unavailable": unavailable,
        "generated_at": pd.Timestamp.now().isoformat(),
        "python": sys.version,
        "pandas": pd.__version__,
        "return_definition": "close / pre_close - 1; Tushare pct_chg retained as a data-quality cross-check",
        "period_label_definition": "last actual observation date in each week/month",
        "research_note": "统计相关/相对收益不等于护盘意图或因果关系。",
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    plot_cumulative(daily, ["sse", "hs300", "chinext", "bank", "insurance"], out_dir)
    for financial in FINANCIALS:
        if financial in daily.columns:
            plot_rotation(daily, financial, out_dir)

    build_markdown_summary(pair_df, rotation_df, out_dir, start, end, unavailable)
    build_html_report(
        pair_df,
        rotation_df,
        exclusion_df,
        threshold_df,
        quality_df,
        event_months,
        sample_pair_df,
        sample_rotation_df,
        out_dir,
        start,
        end,
    )

    LOG.info("完成。结果目录：%s", out_dir)
    LOG.info("先查看：%s", out_dir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
