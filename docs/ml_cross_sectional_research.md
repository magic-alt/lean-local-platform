# CSI300 横截面机器学习研究

首版机器学习能力是研究工作流，不是交易策略。它使用当时可见的 CSI300 成分、证券名称/ST 区间、申万 2021 一级行业、日频行情与公告日对齐财务数据，训练 LightGBM 横截面排序模型。模型结果不会直接进入 LEAN、Paper 或实盘。

## 使用流程

1. 启动应用栈：

   ```bash
   docker compose --profile app up -d --build \
     mysql redis api worker data-worker data-lineage-worker data-demand-worker backtest-worker mlflow ml-worker beat
   ```

2. 在“研究工作台”选择“CSI300 横截面机器学习”，样本开始日保持 `2015-01-01` 或更晚。
3. 运行“数据预检”。若缺少历史估值、财务、ST 或申万行业，点击“准备 PIT 训练数据”。该任务在 `data-bulk` 队列运行，并冻结所选期间的历史成分并集与 SHA-256。
   日线、CSI300 基准或可交易状态属于平台的核心行情前置条件；若预检报告这些缺口，应先运行常规 TuShare 数据同步，再执行本模板的 PIT 专项准备。
4. 数据准备完成后重新预检，再提交研究。训练由单并发 `ml` worker 执行，UI 每四秒刷新阶段和进度。
5. 研究完成后查看滚动样本外与最终冻结样本的 Rank IC、年化 ICIR、NDCG@10/30、Precision@30、五分组收益、Q5-Q1、单调性、特征重要性与建议门槛。MLflow 链接可查看父运行、每折候选子运行和注册的研究模型版本。

## 固定研究契约

- 股票池：每日 PIT CSI300 成分，上市至少 250 个交易日，非历史 ST、非停牌；
- 特征：32 个价格、成交、估值、规模和公告日对齐财务特征；
- 标签：收盘后产生信号，从下一交易日未复权开盘到第 5 个交易日未复权收盘，配合复权因子计算并扣除同期 CSI300 对数收益；
- 排序标签：每日横截面五档，最高 20% 为 4；少于 150 只股票的日期不产生标签；
- 预处理：每日 1%/99% 缩尾、申万一级行业去均值、规模残差化、标准化；缺失值保留给 LightGBM；
- 验证：5 年训练、6 个月验证、3 个月样本外，向前滚动 3 个月；标签边界 purge 5 个交易日、embargo 5 个交易日；最后完整 12 个月不参与调参；
- 模型：8 组固定参数的 `LGBMRanker(objective=lambdarank)`，验证 Rank IC 优先、NDCG@30 次优，并以更简单模型打破平局；
- 建议门槛：滚动样本外和最终冻结样本都要求平均 Rank IC ≥ 0.02、年化 ICIR ≥ 0.5、Q5-Q1 > 0。未达标不等于任务失败。

## 存储与运维

派生特征写入 `LEAN_PARQUET_DIR/ml/feature-sets/<fingerprint>/panel.parquet`；预测、模型和重要性写入 `LEAN_PARQUET_DIR/ml/training-runs/<run-id>/`。平台 MySQL 保存特征集、文件校验和、训练、候选、预测文件和 MLflow 映射；最终模型另存到现有 `stored_objects`。MLflow 使用独立 `lean_mlflow` schema 和 `mlflow-artifacts` volume，仅通过回环端口开放 UI。

定时 MySQL 备份在应用 Compose 配置下同时包含 `lean_market` 与 `lean_mlflow`。模型文本、预测 Parquet 和特征文件仍需纳入数据目录的外部备份；数据库备份不替代这些文件。

## 当前边界

- 尚未实现 ML 分数到 LEAN 信号的导出；请求回测草稿会返回 `409 ML_SIGNAL_EXPORT_NOT_IMPLEMENTED`。
- 尚未实现组合优化、交易成本回测、Paper、Qlib、Optuna、SHAP、深度学习或新闻/公告文本模型。
- `index_member_all` 的申万行业只有调入/调出有效区间，没有独立公告时间，因此它是 effective-time PIT 证据，不宣称完整双时态。
- 数据覆盖门槛是阻断条件；研究表现门槛只是建议状态，不能用于自动晋级生产。


