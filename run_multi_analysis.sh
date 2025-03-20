#!/bin/bash
# =====================================================================
# GitHub 多仓库并发分析执行脚本
# 
# 该脚本用于运行 GitHub 多仓库数据并发收集工具，可以同时分析多个仓库
# 支持通过仓库列表文件或单个仓库指定
# =====================================================================

# 设置默认值
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="multi_repo_analyzer.py"  # 多仓库分析脚本
DEFAULT_TOKEN="ghp_your_token_here"     # 请替换为您的默认 GitHub Token
DEFAULT_WORKERS=3                       # 默认并发线程数
LOG_FILE="multi_repo_analyzer_$(date +%Y%m%d_%H%M%S).log"
DATA_DIR="github_data"
REPO_LIST_FILE=""

# 默认数据收集限制
DEFAULT_COMMITS=500
DEFAULT_ISSUES=200
DEFAULT_PRS=200
DEFAULT_CONTRIBUTORS=100
DEFAULT_STARS=100
DEFAULT_EVENT_PAGES=5
DEFAULT_ACTIVITY_DAYS=90
DEFAULT_DIRECT_PUSH_DAYS=30

# ANSI 颜色代码
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# =========================
# 功能函数
# =========================

# 显示脚本使用帮助
show_help() {
    echo -e "${BLUE}GitHub 多仓库并发分析工具${NC}"
    echo
    echo "使用方法:"
    echo "  $0 [选项]"
    echo
    echo "选项:"
    echo "  -h, --help                 显示此帮助信息"
    echo "  -t, --token TOKEN          GitHub API 访问令牌 (必需)"
    echo "  -l, --list FILE            包含仓库列表的文件 (格式: owner/repo，每行一个)"
    echo "  -r, --repo OWNER/REPO      单个仓库 (格式: owner/repo)"
    echo "  -w, --workers N            最大并发线程数 (默认: $DEFAULT_WORKERS)"
    echo "  -d, --data-dir DIR         数据存储目录 (默认: $DATA_DIR)"
    echo "  --log FILE                 日志文件 (默认: 自动生成)"
    echo
    echo "分析类型 (仅适用于单仓库模式，对于列表模式请在文件中指定):"
    echo "  --all                      收集所有数据 (默认)"
    echo "  --overview                 仅获取仓库概览"
    echo "  --commits                  仅获取提交历史"
    echo "  --activity                 仅获取活动摘要"
    echo
    echo "数据收集参数 (默认为合理的限制值):"
    echo "  --commits-limit N          收集的最大提交数 (默认: $DEFAULT_COMMITS)"
    echo "  --issues-limit N           收集的最大问题数 (默认: $DEFAULT_ISSUES)"
    echo "  --prs-limit N              收集的最大PR数 (默认: $DEFAULT_PRS)"
    echo "  --contributors-limit N     收集的最大贡献者数 (默认: $DEFAULT_CONTRIBUTORS)"
    echo "  --stars-limit N            收集的最大Star用户数 (默认: $DEFAULT_STARS)"
    echo "  --event-pages N            事件页数获取量 (默认: $DEFAULT_EVENT_PAGES)"
    echo "  --activity-days N          活动分析时间范围（天） (默认: $DEFAULT_ACTIVITY_DAYS)"
    echo "  --direct-push-days N       直接推送分析时间范围（天） (默认: $DEFAULT_DIRECT_PUSH_DAYS)"
    echo
    echo "仓库列表文件格式示例:"
    echo "  # 注释行以#开头"
    echo "  microsoft/vscode:all       # 收集所有数据"
    echo "  apache/kafka:activity      # 仅收集活动摘要"
    echo "  torvalds/linux:commits     # 仅收集提交历史"
    echo "  kubernetes/kubernetes      # 不指定类型则默认为all"
    echo
    echo "示例:"
    echo "  $0 -t YOUR_TOKEN -l repos.txt -w 5"
    echo "  $0 -t YOUR_TOKEN -r microsoft/vscode --activity --activity-days 30"
    echo
}

# 记录日志
log() {
    local level=$1
    local message=$2
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    case $level in
        "INFO")
            echo -e "${GREEN}[INFO]${NC} $timestamp - $message" | tee -a "$LOG_FILE"
            ;;
        "WARNING")
            echo -e "${YELLOW}[WARNING]${NC} $timestamp - $message" | tee -a "$LOG_FILE"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $timestamp - $message" | tee -a "$LOG_FILE"
            ;;
        *)
            echo -e "$timestamp - $message" | tee -a "$LOG_FILE"
            ;;
    esac
}

# 验证 Python 环境
check_python() {
    if ! command -v python3 &> /dev/null; then
        log "ERROR" "未找到 python3 命令，请安装 Python 3"
        exit 1
    fi
    
    # 检查必要的 Python 库
    python3 -c "import requests, json, concurrent.futures" 2>/dev/null
    if [ $? -ne 0 ]; then
        log "ERROR" "缺少必要的 Python 库，请运行: pip install requests"
        exit 1
    fi
}

# 验证仓库列表文件
check_repo_list() {
    local file=$1
    if [ ! -f "$file" ]; then
        log "ERROR" "仓库列表文件不存在: $file"
        exit 1
    fi
    
    # 确保文件内容有效
    local count=$(grep -c -E '^[^#]' "$file" | grep -v '^\s*$')
    if [ $count -eq 0 ]; then
        log "ERROR" "仓库列表文件为空或格式无效"
        exit 1
    fi
    
    log "INFO" "仓库列表文件有效: $file"
}

# =========================
# 主程序
# =========================

# 解析命令行参数
TOKEN="$DEFAULT_TOKEN"
WORKERS="$DEFAULT_WORKERS"
REPO=""
ANALYSIS_TYPE="all"
COMMITS_LIMIT="$DEFAULT_COMMITS"
ISSUES_LIMIT="$DEFAULT_ISSUES"
PRS_LIMIT="$DEFAULT_PRS"
CONTRIBUTORS_LIMIT="$DEFAULT_CONTRIBUTORS"
STARS_LIMIT="$DEFAULT_STARS"
EVENT_PAGES="$DEFAULT_EVENT_PAGES"
ACTIVITY_DAYS="$DEFAULT_ACTIVITY_DAYS"
DIRECT_PUSH_DAYS="$DEFAULT_DIRECT_PUSH_DAYS"

# 解析长选项和短选项
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -t|--token)
            TOKEN="$2"
            shift 2
            ;;
        -l|--list)
            REPO_LIST_FILE="$2"
            shift 2
            ;;
        -r|--repo)
            REPO="$2"
            shift 2
            ;;
        -w|--workers)
            WORKERS="$2"
            shift 2
            ;;
        -d|--data-dir)
            DATA_DIR="$2"
            shift 2
            ;;
        --log)
            LOG_FILE="$2"
            shift 2
            ;;
        --all)
            ANALYSIS_TYPE="all"
            shift
            ;;
        --overview)
            ANALYSIS_TYPE="overview"
            shift
            ;;
        --commits)
            ANALYSIS_TYPE="commits"
            shift
            ;;
        --activity)
            ANALYSIS_TYPE="activity"
            shift
            ;;
        --commits-limit)
            COMMITS_LIMIT="$2"
            shift 2
            ;;
        --issues-limit)
            ISSUES_LIMIT="$2"
            shift 2
            ;;
        --prs-limit)
            PRS_LIMIT="$2"
            shift 2
            ;;
        --contributors-limit)
            CONTRIBUTORS_LIMIT="$2"
            shift 2
            ;;
        --stars-limit)
            STARS_LIMIT="$2"
            shift 2
            ;;
        --event-pages)
            EVENT_PAGES="$2"
            shift 2
            ;;
        --activity-days)
            ACTIVITY_DAYS="$2"
            shift 2
            ;;
        --direct-push-days)
            DIRECT_PUSH_DAYS="$2"
            shift 2
            ;;
        *)
            log "ERROR" "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 检查是否提供了 token
if [ "$TOKEN" = "$DEFAULT_TOKEN" ]; then
    log "ERROR" "请提供 GitHub API 访问令牌 (--token)"
    exit 1
fi

# 检查是否提供了仓库列表或单个仓库
if [ -z "$REPO_LIST_FILE" ] && [ -z "$REPO" ]; then
    log "ERROR" "请提供仓库列表文件 (--list) 或单个仓库 (--repo)"
    exit 1
fi

# 如果同时提供了仓库列表和单个仓库，优先使用仓库列表
if [ -n "$REPO_LIST_FILE" ] && [ -n "$REPO" ]; then
    log "WARNING" "同时提供了仓库列表和单个仓库，将使用仓库列表"
    REPO=""
fi

# 检查 Python 环境
check_python

# 如果是仓库列表模式，验证文件
if [ -n "$REPO_LIST_FILE" ]; then
    check_repo_list "$REPO_LIST_FILE"
fi

# 确保数据目录存在
mkdir -p "$DATA_DIR"

# 构建命令参数
CMD_ARGS="--token $TOKEN --data-dir $DATA_DIR --workers $WORKERS"
CMD_ARGS="$CMD_ARGS --commits $COMMITS_LIMIT --issues $ISSUES_LIMIT --prs $PRS_LIMIT"
CMD_ARGS="$CMD_ARGS --contributors $CONTRIBUTORS_LIMIT --stars $STARS_LIMIT"
CMD_ARGS="$CMD_ARGS --event-pages $EVENT_PAGES --activity-days $ACTIVITY_DAYS"
CMD_ARGS="$CMD_ARGS --direct-push-days $DIRECT_PUSH_DAYS"

# 添加仓库来源参数
if [ -n "$REPO_LIST_FILE" ]; then
    CMD_ARGS="$CMD_ARGS --repo-list $REPO_LIST_FILE"
else
    CMD_ARGS="$CMD_ARGS --owner-repo $REPO --analysis-type $ANALYSIS_TYPE"
fi

# 启动分析
log "INFO" "启动多仓库分析，时间: $(date)"
log "INFO" "并发线程数: $WORKERS"

# 构建并执行命令
CMD="python3 $PYTHON_SCRIPT $CMD_ARGS"
log "INFO" "执行命令: $CMD"

# 执行命令并记录输出
$CMD 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    log "INFO" "分析完成，时间: $(date)"
else
    log "ERROR" "分析失败，退出代码: $EXIT_CODE"
fi

log "INFO" "日志文件: $LOG_FILE"
log "INFO" "数据已保存到目录: $DATA_DIR"

exit $EXIT_CODE