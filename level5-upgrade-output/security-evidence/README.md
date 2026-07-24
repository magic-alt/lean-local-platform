# Security evidence

当前 inspect 仍显示 `backtest-worker` 挂载 raw Docker socket，且拥有可写仓库/Data
mount。Compose 仍含仓库已知默认凭据，Redis 没有认证。本轮没有执行会影响现有
数据卷的凭据轮换，也没有伪造关闭结论。
