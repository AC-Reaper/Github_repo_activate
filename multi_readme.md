# GitHub 多仓库并发分析工具

该工具扩展了原有的 GitHub 仓库分析功能，支持并发分析多个仓库，显著提高了数据收集效率。

## 功能特点

* **并发分析** ：同时分析多个 GitHub 仓库，充分利用 API 配额
* **灵活配置** ：支持每个仓库单独配置分析类型和深度
* **实时监控** ：分析过程中实时更新状态和进度
* **自动重试** ：自动处理 API 限制和临时错误，确保数据完整性
* **详细报告** ：生成完整的分析报告，包括成功、失败和异常详情

## 文件结构

```
.
├── multi_repo_analyzer.py        # 多仓库并发分析脚本
├── run_multi_analysis.sh         # Shell 脚本封装
├── repo_list_example.txt         # 仓库列表文件示例
├── github_repo_analyzer.py       # 仓库分析器核心实现
├── github_api_client.py          # GitHub API 客户端
├── data_storage.py               # 数据存储处理
└── README.md                     # 项目文档
```

## 安装与准备

1. 克隆或下载仓库
2. 安装必要的依赖:
   ```bash
   pip install requests
   ```
3. 为脚本添加执行权限:
   ```bash
   chmod +x run_multi_analysis.sh
   ```
4. 准备 GitHub 个人访问令牌:
   * 访问 GitHub > Settings > Developer settings > Personal access tokens
   * 创建新令牌，至少需要 `repo` 权限

## 使用方法

### 方法一：使用 Shell 脚本

```bash
./run_multi_analysis.sh -t YOUR_TOKEN -l repo_list.txt -w 5
```

#### 主要选项:

* `-t, --token TOKEN`: GitHub API 访问令牌（必需）
* `-l, --list FILE`: 仓库列表文件（每行一个仓库）
* `-r, --repo OWNER/REPO`: 单个仓库（与 `-l` 互斥）
* `-w, --workers N`: 最大并发线程数（默认: 3）
* `-d, --data-dir DIR`: 数据存储目录（默认: github_data）

#### 分析类型（仅适用于单仓库模式）:

* `--all`: 收集所有数据（默认）
* `--overview`: 仅获取仓库概览
* `--commits`: 仅获取提交历史
* `--activity`: 仅获取活动摘要

#### 数据收集限制:

* `--commits-limit N`: 最大提交数（默认: 500）
* `--issues-limit N`: 最大问题数（默认: 200）
* `--prs-limit N`: 最大PR数（默认: 200）
* 更多选项查看帮助: `./run_multi_analysis.sh --help`

### 方法二：直接使用 Python 脚本

```bash
python3 multi_repo_analyzer.py --token YOUR_TOKEN --repo-list repo_list.txt --workers 5
```

### 仓库列表文件格式

仓库列表文件每行指定一个仓库，格式为 `owner/repo[:analysis_type]`，例如:

```
# 注释以#开头
microsoft/vscode:overview   # 仅获取概览
apache/kafka:activity       # 仅获取活动摘要
google/gson                 # 不指定则默认为all
```

可用的分析类型:

* `all`: 收集所有数据
* `overview`: 仅获取仓库概览
* `commits`: 仅获取提交历史
* `activity`: 仅获取活动摘要

## 示例场景

### 场景一：监控多个项目的活动状态

```bash
# 创建仓库列表
cat > repo_monitor.txt << EOF
kubernetes/kubernetes:activity
istio/istio:activity
prometheus/prometheus:activity
helm/helm:activity
EOF

# 运行分析
./run_multi_analysis.sh -t YOUR_TOKEN -l repo_monitor.txt -w 4 --activity-days 30
```

### 场景二：收集提交历史进行代码贡献分析

```bash
# 创建仓库列表
cat > code_analysis.txt << EOF
tensorflow/tensorflow:commits
pytorch/pytorch:commits
scikit-learn/scikit-learn:commits
EOF

# 运行分析
./run_multi_analysis.sh -t YOUR_TOKEN -l code_analysis.txt -w 3 --commits-limit 1000
```

### 场景三：获取单个大型仓库的完整数据

```bash
./run_multi_analysis.sh -t YOUR_TOKEN -r facebook/react --all
```

## 输出与结果

分析结果将存储在指定的数据目录中（默认为 `github_data`）:

1. 每个仓库的数据存储在独立的子目录 `github_data/owner_repo/`
2. 汇总报告保存在 `github_data/multi_analysis_TIMESTAMP/` 目录下
3. 主要输出文件:
   * `analysis_summary.json`: 包含所有仓库分析结果的汇总报告
   * `analysis_complete.txt`: 简明的分析完成情况报告

## 处理 API 限制

GitHub API 有速率限制（使用令牌时为每小时 5,000 个请求）。为避免触发限制:

1. 设置合理的并发线程数（通常 3-5 个）
2. 使用 `--overview` 或 `--activity` 减少数据获取量
3. 为大型仓库设置合理的数据限制（如最大提交数）
4. 程序内置了自动速率监控和等待逻辑

## 注意事项

1. **API 令牌安全** : 不要在公共环境泄露您的 GitHub 令牌
2. **大型仓库** : 非常大的仓库（如 Linux 内核）分析可能需要很长时间
3. **错误处理** : 程序设计为自动处理临时错误和速率限制，但不完全保证成功
4. **数据存储** : 大量仓库分析可能生成几百 MB 的数据

## 排障指南

### 无法连接到 GitHub API

* 检查网络连接
* 确认 GitHub API 访问令牌有效

### 分析过程中出现大量错误

* 检查令牌权限
* 考虑减少并发线程数
* 扩大存储空间

### API 速率限制问题

* 减少一次分析的仓库数量
* 降低数据收集深度（使用 `overview` 而非 `all`）
* 为大型仓库设置更严格的限制

## 扩展与定制

可以通过以下方式扩展工具功能:

1. 修改 `github_repo_analyzer.py` 添加新的分析类型
2. 更新 `multi_repo_analyzer.py` 支持更多并行处理选项
3. 添加数据后处理和可视化功能
