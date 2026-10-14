# wait-until

> 等到服务真正就绪再往下跑：URL / 端口 / 文件 / 日志行 / 命令。零依赖 Python CLI。

Block until a URL, TCP port, file, log line, or command is ready. Stdlib only.

适合本地脚本、CI，以及容易「起服务后立刻打接口」的 AI Agent。

---

## 做什么

常见场景：

- 本地起了 Vite / Spring Boot / Docker，但端口还没 listen
- Agent 起了后台进程，下一句就要 `curl`
- CI 里要等健康检查通过再跑测试

`wait-until` 轮询直到条件满足（退出码 0），或超时（退出码 1）。

| 子命令 | 含义 |
|--------|------|
| `url`  | HTTP(S) 返回 2xx/3xx（或指定状态码） |
| `port` | TCP 能连上 |
| `file` | 文件出现（可选非空） |
| `log`  | 日志里出现某段文字 |
| `cmd`  | 外部命令退出码为 0 |

## 安装 / 打开

需要 Python 3.8+（系统自带即可）：

```bash
git clone https://github.com/temptation2017/wait-until.git
cd wait-until
python3 wait_until.py --help
```

也可把 `wait_until.py` 拷到 PATH，并改名为 `wait-until`：

```bash
cp wait_until.py ~/.local/bin/wait-until
chmod +x ~/.local/bin/wait-until
```

## 怎么用

```bash
# 等本地网页起来（默认最多 60 秒，每秒查一次）
python3 wait_until.py url http://127.0.0.1:3000/

# 等健康检查返回精确 200
python3 wait_until.py url http://127.0.0.1:8080/health --status 200 -t 120

# 等端口（默认主机 127.0.0.1）
python3 wait_until.py port 5432
python3 wait_until.py port 127.0.0.1:6379 -t 30 -i 0.5

# 等构建产物出现且非空
python3 wait_until.py file ./dist/index.js --non-empty -t 90

# 等日志出现启动成功字样（默认只看「启动本命令之后」的新内容）
python3 wait_until.py log ./app.log "Started Application"

# 从文件开头扫（适合日志里已经写好了）
python3 wait_until.py log ./app.log READY --from-start

# 等某条命令变绿（例如数据库可连）
python3 wait_until.py cmd -t 60 -- pg_isready -h 127.0.0.1

# 安静模式：只靠退出码
python3 wait_until.py port 3000 -q
```

### 退出码

| 码 | 含义 |
|----|------|
| 0 | 条件已满足 |
| 1 | 超时或检查失败到底 |
| 2 | 参数错误 |

## 示例（Agent / CI 片段）

```bash
# 后台起服务，再等就绪，再跑测试（虚构示例）
npm run dev &
python3 wait_until.py url http://127.0.0.1:5173/ -t 60
npm test
```

```bash
# Docker Compose 起来后等 Postgres
docker compose up -d
python3 wait_until.py port 5432 -t 90
python3 wait_until.py cmd -- pg_isready -h 127.0.0.1 -p 5432
```

文字示例：

```text
$ python3 wait_until.py port 18765 -t 5 -i 0.2
[wait-until] waiting up to 5s (every 0.2s): port 127.0.0.1:18765
[wait-until] ready: port 127.0.0.1:18765 (attempt 3)
```

## 限制

- `url` 用的是标准库 `urllib`，不校验自定义证书策略；复杂鉴权请用 `cmd` 包一层 `curl`。
- `log` 匹配是**字面量子串**，不是正则；超大日志会截断内存中的滚动缓冲。
- `port` 只验证 TCP 能 connect，不保证应用协议已就绪（需要时再叠一层 `url` / `cmd`）。
- 单文件、无第三方依赖；不做进程守护，也不替你杀后台任务。

## 可改进点

- 支持正则日志匹配、多条件 AND/OR
- 输出 JSON 事件流方便 Agent 解析
- 内置 `dns` / `tcp+banner` 检查

## License

MIT — 见 [LICENSE](./LICENSE)。
