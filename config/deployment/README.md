# 平台环境变量与凭据配置指南

本文说明如何从 `.env.example` 生成私有 `.env`，以及如何为 Docker、native
和 Windows Dockerless 部署创建账号、密码与 token。示例中的值全是占位符，
不能原样用于部署。

## 1. 文件选择与安全规则

根目录 `.env.example` 是完整变量目录；`config/deployment/` 下的文件是不同
部署拓扑的最小覆盖：

| 文件 | 用途 |
| --- | --- |
| `.env.example` | 完整配置目录，复制为仓库根目录私有 `.env` |
| `docker.env.example` | Docker Compose 拓扑覆盖 |
| `native.env.example` | Linux/开发机 native 拓扑覆盖 |
| `windows-native.env.example` | Windows SCM/Dockerless 绝对路径模板 |

Windows 本机应保存为 `D:\Project\platform\.env`。后端依次加载仓库根目录
`.env` 和 `web/backend/.env`，已存在的进程环境变量优先。生产环境只维护一个
权威来源，避免同名变量在多个位置漂移。

- 不提交 `.env`、token 文件、私钥、证书私钥或密码。
- 不把 `.env` 内容粘贴到聊天、日志、Issue、PR 或截图。
- 每个身份使用独立随机密码；不要复用 PostgreSQL、RabbitMQ、API、runner、
  Windows 服务账户或数据提供商凭据。
- `.env` 使用 `KEY=value`，不要保留 `<...>` 占位符。
- 修改 `.env` 后必须重启 API、worker、beat 和 runner。

## 2. Windows native 必填矩阵

| 类别 | 变量 | 是否必填 | 说明 |
| --- | --- | ---: | --- |
| 模式 | `LEAN_DEPLOYMENT_MODE` | 是 | Windows native 填 `native` |
| 模式 | `LEAN_EXECUTION_BACKEND` | 是 | Windows native 填 `native` |
| 模式 | `LEAN_DEPLOYMENT_PROFILE` | 是 | Core 部署填 `core` |
| API | `LEAN_API_AUTH_REQUIRED` | 是 | 正式环境保持 `1` |
| API | `LEAN_API_TOKEN` 或 `LEAN_API_TOKEN_FILE` | 是 | 平台 API 凭据，不是 TuShare token |
| Runner | `LEAN_RUNNER_TOKEN` 或 `LEAN_RUNNER_TOKEN_FILE` | 是 | 必须与 API token 不同 |
| PostgreSQL | `LEAN_POSTGRES_ADMIN_URL` | 初始化必填 | 仅供角色/数据库初始化与受控恢复 |
| PostgreSQL | `LEAN_POSTGRES_APP_PASSWORD` | 是 | `lean_app` 的原始密码 |
| PostgreSQL | `LEAN_POSTGRES_CELERY_PASSWORD` | 是 | `lean_celery` 的原始密码 |
| PostgreSQL | `LEAN_POSTGRES_MLFLOW_PASSWORD` | 是 | `lean_mlflow` 的原始密码 |
| PostgreSQL | `LEAN_DATABASE_URL` | 是 | API/control plane 连接 URL |
| PostgreSQL | `CELERY_RESULT_BACKEND` | 是 | Celery 结果数据库 URL |
| PostgreSQL | `LEAN_MLFLOW_DATABASE_URL` | 是 | MLflow 数据库 URL |
| RabbitMQ | `CELERY_BROKER_URL` | 是 | `lean_worker` + `lean` vhost 的 AMQP URL |
| Runtime | `LEAN_NATIVE_RUNTIME_ID` | 是 | 必须匹配已审核的 signed runtime lock |
| Runtime | `LEAN_NATIVE_RUNTIME_ROOT` | 是 | Windows SCM 使用绝对路径 |
| Runtime | `LEAN_DOTNET_PATH` | 条件必填 | dotnet 不在 PATH 时填写；部署机只需 .NET 10 Runtime |
| Sandbox | `LEAN_NATIVE_SANDBOX` | 是 | 正式环境保持 `required` |
| Sandbox | `LEAN_WINDOWS_SANDBOX_POLICY_FILE` | 是 | Windows 绝对路径 |
| 服务身份 | `LEAN_WINDOWS_PLATFORM_ACCOUNT` | SCM 必填 | 建议 `.\LeanPlatform` |
| 服务身份 | `LEAN_WINDOWS_PLATFORM_PASSWORD` | 安装时必填 | 独立服务密码 |
| 服务身份 | `LEAN_WINDOWS_RUNNER_ACCOUNT` | SCM 必填 | 建议 `.\LeanRunner` |
| 服务身份 | `LEAN_WINDOWS_RUNNER_PASSWORD` | 安装时必填 | 与平台服务密码不同 |
| 路径 | `LEAN_DATA_DIR`、`LEAN_RUNTIME_DIR`、`LEAN_PARQUET_DIR` | 是 | Windows SCM 全部使用绝对路径 |

`TUSHARE_TOKEN`、`JQDATA_*`、`RQDATA_*` 和各类 LLM `*_API_KEY` 仅在启用
相应提供商时必填。它们不能替代 `LEAN_API_TOKEN`。

## 3. 生成独立随机密码和 token

在 PowerShell 7 中，每执行一次生成一个新的 256-bit 十六进制值：

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

至少分别为 PostgreSQL 管理员、`lean_app`、`lean_celery`、`lean_mlflow`、
RabbitMQ `lean_worker`、平台 API、restricted runner、`LeanPlatform` Windows
服务和 `LeanRunner` Windows 服务生成九个不同值。将值直接存入受控密码管理器，
不要先写到命令历史或临时文本。

十六进制值只含 URL-safe 字符，因此原始值和 URL 中的值相同。如果使用包含特殊
字符的密码，URL 中的密码必须 percent-encode：

```powershell
python -c "import getpass, urllib.parse; print(urllib.parse.quote(getpass.getpass('Password: '), safe=''))"
```

命令输出仍是可逆的敏感凭据，只能写入本机私有 `.env`，不能对外发送。

## 4. PostgreSQL 账号与数据库

PostgreSQL 安装程序创建 `postgres` 管理员及其密码。平台脚本根据管理员 URL
创建或更新以下最小权限身份和数据库：

| 数据库 | 默认角色 | 用途 |
| --- | --- | --- |
| `lean_platform` | `lean_app` | 权威 control plane |
| `lean_celery` | `lean_celery` | 可丢弃的 Celery 结果元数据 |
| `lean_mlflow` | `lean_mlflow` | MLflow 自有 schema |

填写方式：

```dotenv
LEAN_POSTGRES_ADMIN_URL=postgresql://postgres:<URL_ENCODED_ADMIN_PASSWORD>@127.0.0.1:5432/postgres
LEAN_POSTGRES_APP_PASSWORD=<RAW_APP_PASSWORD>
LEAN_POSTGRES_CELERY_PASSWORD=<RAW_CELERY_PASSWORD>
LEAN_POSTGRES_MLFLOW_PASSWORD=<RAW_MLFLOW_PASSWORD>
LEAN_DATABASE_URL=postgresql+psycopg://lean_app:<URL_ENCODED_APP_PASSWORD>@127.0.0.1:5432/lean_platform
CELERY_RESULT_BACKEND=db+postgresql+psycopg://lean_celery:<URL_ENCODED_CELERY_PASSWORD>@127.0.0.1:5432/lean_celery
LEAN_MLFLOW_DATABASE_URL=postgresql+psycopg://lean_mlflow:<URL_ENCODED_MLFLOW_PASSWORD>@127.0.0.1:5432/lean_mlflow
```

从仓库根目录运行唯一正式初始化/迁移入口：

```powershell
web\backend\.venv\Scripts\python.exe scripts\platformctl.py --mode native db init
```

该命令创建/更新角色与数据库并应用平台迁移。API、worker 和 beat 只验证迁移，
不会自行修改 schema。运行主机不应长期给应用进程管理员权限；管理员 URL 仅供
受控初始化、迁移和隔离恢复流程使用。

## 5. RabbitMQ 用户与 vhost

固定应用身份为 `lean_worker`，固定 vhost 为 `lean`。密码由部署者生成，RabbitMQ
不能恢复其明文；遗失时应重置。使用拥有正确 Erlang cookie 的受控运维账户：

```powershell
rabbitmqctl.bat add_vhost lean
rabbitmqctl.bat add_user lean_worker "<RAW_RABBITMQ_PASSWORD>"
rabbitmqctl.bat set_permissions -p lean lean_worker ".*" ".*" ".*"
```

若用户已存在，使用：

```powershell
rabbitmqctl.bat change_password lean_worker "<RAW_RABBITMQ_PASSWORD>"
```

然后填写：

```dotenv
LEAN_RABBITMQ_PASSWORD=<RAW_RABBITMQ_PASSWORD>
CELERY_BROKER_URL=amqp://lean_worker:<URL_ENCODED_RABBITMQ_PASSWORD>@127.0.0.1:5672/lean
```

`LEAN_RABBITMQ_PASSWORD` 供 Compose/bootstrap 使用；应用运行时通过
`CELERY_BROKER_URL` 连接。`rabbitmqctl` 的 Erlang cookie 属于运维认证，不应复制
给普通交互账户。Core Golden 要求真实 AMQP 握手；CLI cookie 问题属于后续生产
运维加固，但 12 小时故障认证前必须解决。

## 6. API、runner 与提供商 token

`LEAN_API_TOKEN` 保护 FastAPI/OpenAPI/metrics；`LEAN_RUNNER_TOKEN` 保护仅绑定
loopback 的 restricted runner。两者都由本机随机生成，且必须不同：

```dotenv
LEAN_API_AUTH_REQUIRED=1
LEAN_API_TOKEN=<RANDOM_API_TOKEN>
LEAN_RUNNER_TOKEN=<DIFFERENT_RANDOM_RUNNER_TOKEN>
```

也可以使用 ACL 受限的 token 文件。若变量和文件同时存在，环境变量优先：

```dotenv
LEAN_API_TOKEN_FILE=C:\ProgramData\LeanPlatform\runtime\secrets\api_token
LEAN_RUNNER_TOKEN_FILE=C:\ProgramData\LeanPlatform\runtime\secrets\runner_token
```

`TUSHARE_TOKEN` 是从 TuShare Pro 账户取得的数据提供商凭据，只用于 TuShare；
它与平台 API token、runner token 没有任何关系。

## 7. Windows 服务账户与 sandbox

在提升权限的 PowerShell 中创建两个非交互本地身份，密码从受控密码管理器读取：

```powershell
$platformPassword = Read-Host "LeanPlatform password" -AsSecureString
New-LocalUser -Name LeanPlatform -Password $platformPassword -PasswordNeverExpires -UserMayNotChangePassword

$runnerPassword = Read-Host "LeanRunner password" -AsSecureString
New-LocalUser -Name LeanRunner -Password $runnerPassword -PasswordNeverExpires -UserMayNotChangePassword
```

不要把普通桌面账户用于 SCM 或 restricted runner。随后配置 sandbox：

```powershell
.\deploy\windows\configure_windows_sandbox.ps1 `
  -RunnerAccount .\LeanRunner `
  -RuntimeRoot C:\ProgramData\LeanPlatform\lean `
  -DotnetPath "C:\Program Files\dotnet\dotnet.exe" `
  -DataRoot D:\LeanPlatform\data `
  -WorkRoot C:\ProgramData\LeanPlatform\runtime `
  -PolicyPath C:\ProgramData\LeanPlatform\sandbox-policy.json
```

服务安装时 `platformctl` 需要两个账号及密码变量。安装完成后由 Windows SCM
持有服务登录凭据；不要在日志或命令行回显密码。

## 8. Native runtime 与 .NET

部署主机只需 .NET 10 Runtime，并通过以下顺序解析 `dotnet.exe`：

```text
LEAN_DOTNET_PATH -> PATH -> C:\Program Files\dotnet\dotnet.exe
```

部署主机不需要 SDK，也不应持有签名私钥。Build/release 主机单独安装 .NET 10
SDK、Python 3.11，并持有受控私钥，用于构建、签名、发布 Windows x64 LEAN
artifact。正式 runtime lock 在真实 artifact 完成审核前必须保持 `supported:false`。

## 9. 启动与脱敏验证

按顺序执行：

```powershell
web\backend\.venv\Scripts\python.exe scripts\platformctl.py --mode native --profile core doctor
web\backend\.venv\Scripts\python.exe scripts\platformctl.py --mode native db init
web\backend\.venv\Scripts\python.exe scripts\platformctl.py --mode native runtime install
web\backend\.venv\Scripts\python.exe scripts\platformctl.py --mode native --profile core start
```

验证重点：

- `doctor` 中 PostgreSQL/RabbitMQ TCP 和 .NET Runtime 为 `READY`；
- 应用层 `/api/health` 中 database 与 broker 为 `ready`；
- RabbitMQ 必须通过 AMQP 认证，端口连通本身不够；
- API/OpenAPI 请求携带 `Authorization: Bearer <LEAN_API_TOKEN>`；
- native runner 必须验证 signed runtime、sandbox policy、ACL、firewall 和服务身份；
- Windows Dockerless Golden 与 12 小时 production certification 是两个独立门禁。

不得为了通过检查关闭 API 认证、放宽 sandbox、恢复 Docker fallback，或将 runtime
lock 改为 `supported:true`。P9 未启用；普通部署验证不得执行 broker 写入或 live
activation。
