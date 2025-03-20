# GitHub 仓库活动分析工具

这是一个用于分析 GitHub 仓库活动的工具，通过 GitHub API 收集仓库的各种数据，并进行分析和统计。该工具可以帮助您了解仓库的活跃度、贡献者情况、代码提交模式等信息。

## 功能特点

* **仓库概览** ：获取仓库的基本信息和统计数据
* **提交历史** ：分析代码提交历史，包括直接提交和通过 PR 提交的情况
* **贡献者分析** ：了解谁参与了项目以及贡献程度
* **分支管理** ：获取分支详情和分支相关事件（创建、删除）
* **强制推送检测** ：识别强制推送事件，这可能表明代码历史被重写
* **PR 和 Issue 分析** ：收集和分析 PR 和 Issue 的数据
* **Star 用户分析** ：了解谁对项目感兴趣
* **仓库活动摘要** ：生成仓库近期活动的摘要报告

## 项目结构

```
.
├── main.py                    # 主入口文件
├── github_repo_analyzer.py    # 仓库分析器核心实现
├── github_api_client.py       # GitHub API 客户端
├── data_storage.py            # 数据存储处理
├── analyze_repo.sh            # Shell 脚本封装
└── README.md                  # 项目文档
```

## 依赖项

* Python 3.7+
* 依赖库：
  * requests
  * argparse
  * datetime
  * json
  * time
  * os

## 安装和设置

1. 克隆或下载此仓库
2. 安装依赖库：
   ```bash
   pip install requests
   ```
3. 为脚本添加执行权限：
   ```bash
   chmod +x analyze_repo.sh
   ```
4. 获取 GitHub 个人访问令牌：
   * 访问 GitHub > Settings > Developer settings > Personal access tokens
   * 创建一个新的令牌，至少需要具有 `repo` 权限

## 使用方法

### 通过 Shell 脚本运行

```bash
./analyze_repo.sh -t YOUR_TOKEN -o OWNER -r REPO [选项]
```

示例：

```bash
# 分析 Microsoft/VSCode 仓库的所有数据
./analyze_repo.sh -t ghp_abc123 -o microsoft -r vscode -a

# 仅获取 Apache/Kafka 仓库的最近 30 天活动摘要
./analyze_repo.sh -t ghp_abc123 -o apache -r kafka --activity-only --activity-days 30

# 仅获取 Torvalds/Linux 仓库的最近 200 次提交
./analyze_repo.sh -t ghp_abc123 -o torvalds -r linux --commits-only --commits 200
```

### 直接运行 Python 脚本

```bash
python main.py --token YOUR_TOKEN --owner OWNER --repo REPO [选项]
```

示例：

```bash
# 分析 Microsoft/VSCode 仓库的所有数据
python main.py --token ghp_abc123 --owner microsoft --repo vscode --all

# 仅获取 Apache/Kafka 仓库的活动摘要
python main.py --token ghp_abc123 --owner apache --repo kafka --activity-only
```

## 命令行选项

### 必需选项

* `--token TOKEN`：GitHub API 访问令牌
* `--owner OWNER`：仓库所有者
* `--repo REPO`：仓库名称

### 数据收集选项

* `--all`：收集所有数据（默认行为）
* `--overview`：仅获取仓库概览
* `--commits-only`：仅获取提交历史
* `--activity-only`：仅获取活动摘要
* `--pr-only`：仅获取 PR
* `--issues-only`：仅获取问题
* `--contributors-only`：仅获取贡献者
* `--branches-only`：仅获取分支信息
* `--events-only`：仅获取事件历史

### 限制选项

* `--commits N`：最大提交获取数量
* `--issues N`：最大问题获取数量
* `--prs N`：最大 PR 获取数量
* `--contributors N`：最大贡献者获取数量
* `--stars N`：最大 Star 用户获取数量
* `--event-pages N`：事件页数获取量（默认：5）
* `--activity-days N`：活动分析时间范围（天）（默认：90）
* `--direct-push-days N`：直接推送分析时间范围（天）（默认：30）

### 其他选项

* `--data-dir DIR`：数据存储目录（默认：`github_data`）

## 数据输出

所有收集到的数据都以 JSON 格式存储在 `data_dir/owner_repo/` 目录下，每种数据类型都有单独的 JSON 文件，并带有时间戳。

主要数据文件包括：

| 文件前缀          | 描述             |
| ----------------- | ---------------- |
| overview_         | 仓库基本信息     |
| commits_          | 提交历史         |
| issues_           | 问题列表         |
| pull_requests_    | PR 列表          |
| contributors_     | 贡献者信息       |
| branches_         | 分支详情         |
| detailed_events_  | 仓库事件         |
| force_pushes_     | 强制推送记录     |
| branch_events_    | 分支创建删除事件 |
| direct_pushes_    | 直接提交记录     |
| activity_summary_ | 活动摘要         |
| complete_data_    | 完整数据集元数据 |

## API 使用说明

### 主要类

#### `GitHubRepoAnalyzer`

```python
analyzer = GitHubRepoAnalyzer(token="YOUR_TOKEN", owner="owner", repo="repo")

# 获取仓库概览
overview = analyzer.get_repo_overview()

# 获取提交历史
commits = analyzer.get_commit_history(max_items=500)

# 生成活动摘要
summary = analyzer.get_repo_activity_summary(since_days=90)

# 收集所有数据
all_data = analyzer.collect_all_data()
```

#### `DataStorage`

```python
storage = DataStorage(owner="owner", repo="repo", data_dir="data")

# 保存数据
storage.save_data("my_data", {"key": "value"})

# 加载最新数据
data = storage.load_data("my_data")

# 查看存储信息
info = storage.get_storage_info()
```

## 注意事项

1. **API 速率限制** ：GitHub API 有速率限制，使用令牌可以获得更高的限制（每小时 5000 个请求）
2. **大型仓库** ：对于大型仓库，收集完整数据可能需要较长时间
3. **权限** ：某些 API 功能（如流量统计）需要具有仓库管理员权限的令牌才能访问
4. **敏感信息** ：不要在公共场合暴露您的 GitHub 令牌

## 常见问题排查

### 速率限制错误

如果遇到 `达到 API 速率限制` 错误，脚本会自动等待限制重置后继续。对于大型仓库，可以使用限制选项减少数据获取量。

### 授权错误

如果遇到 `资源未找到或无权访问` 错误，请确保：

* 令牌有正确的权限
* 仓库名称和所有者拼写正确
* 对于私有仓库，令牌必须有访问该仓库的权限

### 请求错误

如果遇到网络问题，脚本会自动重试。但如果持续失败，请检查网络连接。

## 扩展与定制

该工具设计为模块化的，可以轻松扩展和定制。如需添加新功能，可以：

1. 在 `github_repo_analyzer.py` 中添加新的方法
2. 在 `main.py` 中添加相应的命令行参数
3. 在 `analyze_repo.sh` 中更新脚本选项

## 贡献

欢迎提交问题报告、功能请求和代码贡献。请遵循以下步骤：

1. Fork 此仓库
2. 创建您的特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交您的更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 打开一个 Pull Request

## 许可证

[MIT License](https://claude.ai/chat/LICENSE)

## 免责声明

此工具仅用于信息收集和分析目的。请遵守 GitHub 的服务条款和 API 使用条款。滥用此工具可能会导致您的 GitHub 账户被限制。
