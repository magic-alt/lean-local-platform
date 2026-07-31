# A股银行/保险与大盘、创业板关系研究包

## 1. 研究问题

这套代码区分三种完全不同的命题：

1. **绝对反向**：市场下跌时银行/保险本身上涨，市场上涨时银行/保险本身下跌。
2. **相对防御**：市场下跌时银行/保险虽然也可能下跌，但跌得更少；市场上涨时它们涨得更少或跑输。
3. **价值—成长轮动**：银行相对沪深300的收益，与创业板相对沪深300的收益呈负相关。

不能用第 2 或第 3 种现象直接证明“护盘意图”。

## 2. 安装

```bash
pip install -r requirements_financial_rotation.txt
```

设置 token：

```bash
# Linux/macOS
export TUSHARE_TOKEN='你的token'

# Windows PowerShell
$env:TUSHARE_TOKEN='你的token'
```

## 3. 运行五年研究

```bash
python a_share_financial_rotation_study.py \
  --start 20210802 \
  --end 20260730 \
  --out results_20210802_20260730
```

截至 2026-07-31 午间，7 月 31 日仍未收盘，因此示例使用 2026-07-30，避免把不完整交易日放入月度结果。

## 4. 默认指数

| 内部名 | 指数 | Tushare 代码 |
|---|---|---|
| sse | 上证综指 | 000001.SH |
| szse_component | 深证成指 | 399001.SZ |
| szse_a | 深证A指 | 399107.SZ |
| chinext | 创业板指 | 399006.SZ |
| hs300 | 沪深300 | 000300.SH |
| bank | 中证银行 | 399986.SZ |
| insurance | 保险主题 | 399809.SZ |

`399001.SZ` 是深证成指，并不代表深市全部股票；研究“深市大盘”时建议同时看 `399107.SZ`。

## 5. 主要输出

- `pair_statistics.csv`：相关系数、同向率、条件命中率、HAC 回归 beta。
- `threshold_statistics.csv`：0、±0.5%、±1.0% 和收益尾部 10% 的状态检验。
- `rotation_statistics.csv`：银行/保险相对沪深300与创业板相对沪深300的轮动回归。
- `rotation_winsorized.csv`：5%/95% 去极值稳健性。
- `rotation_excluding_2026_06_07.csv`：剔除 2026 年 6—7 月后的稳健性。
- `sample_window_pair_monthly.csv`、`sample_window_rotation_monthly.csv`：样本窗口敏感性。
- `rolling_statistics_daily.csv`：60/120/250 日滚动相关和 beta。
- `yearly_statistics_daily.csv`：逐年稳定性。
- `data_quality.csv`：日期、缺失、重复和收益字段交叉核验。
- `returns_daily.csv`、`returns_weekly.csv`、`returns_monthly.csv`：标准化收益面板。
- `summary.md`：自动生成的中文结果摘要。
- `verification_report.html`：自动生成的完整中文复核报告。

收益优先使用 Tushare 的 `close / pre_close - 1`；`pct_chg` 仅用于精度交叉核验。周频和月频输出使用该周期最后一个实际观测日作为日期标签，避免把不完整周期误标为已经完整收盘。

## 6. 判定标准

### 命题 A：绝对反向

至少同时满足：

- `fin_up_when_market_down_rate` 显著高于 50%；
- `fin_down_when_market_up_rate` 显著高于 50%；
- `ols_beta < 0` 且 HAC p 值显著；
- 日频、周频、月频以及各年度大体一致。

只满足一两个阶段，不足以称为稳定规律。

### 命题 B：相对防御

观察：

- 市场跌时 `fin_outperform_when_market_down_rate` 是否显著高于 50%；
- 市场涨时 `fin_underperform_when_market_up_rate` 是否显著高于 50%；
- 条件平均相对收益是否方向一致。

这允许“银行也跌，只是跌得较少”。

### 命题 C：价值—成长轮动

模型：

```text
金融相对沪深300收益_t
= α + β ×（创业板相对沪深300收益_t）+ ε_t
```

若 `β` 稳定显著为负，说明主要关系是风格轮动，而不是“市场涨跌的机械反向”。

## 7. 精确测算指数点位贡献

只看中证银行和上证综指的涨跌，不足以证明银行“拉指数”。更严格的计算是：

```text
金融贡献收益_t = Σ(成分股前一日权重_i,t-1 × 成分股收益_i,t)
金融贡献点数_t ≈ 指数前一日收盘点位 × 金融贡献收益_t
其余板块贡献_t = 指数总收益_t - 金融贡献收益_t
```

建议定义“金融支撑日”：

```text
其余板块贡献 < 0 且 金融贡献 > 0
```

所需 Tushare 数据：

- `index_weight`：历史指数成分及权重；
- `daily`：成分股日收益；
- `index_member_all`：申万行业历史成员，必须按日期处理；
- `daily_basic`：总市值、流通市值、换手率等控制变量；
- `sw_daily`：申万银行、保险等行业指数的替代口径。

不要使用今天的行业成分表回填过去五年，否则会产生前视偏差和幸存者偏差。

## 8. 因果与“护盘”识别

收盘价统计只能验证共振、相对防御和轮动，不能识别资金身份或政策意图。更接近事件研究的设计还需要：

- 分钟级数据，观察金融板块是否在指数急跌后才异常拉升；
- 对比历史正常日的异常收益和异常成交；
- 中央汇金、ETF 增持等公开事件时间戳；
- 控制利率、国债收益率曲线、红利风格、估值、成交拥挤度和季度调仓。

因此应将结论表述为“金融板块在某类市场状态下提供了正向点位贡献”，而不是仅凭价格关系断言“有人护盘”。
