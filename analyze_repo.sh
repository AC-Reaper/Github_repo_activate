#!/bin/bash
# =====================================================================
# GitHub仓库数据分析执行脚本
# 
# 该脚本用于运行GitHub仓库数据收集工具，基于GraphQL API高效获取仓库数据。
# 支持分析单个仓库或批量分析多个仓库，默认全量获取数据。
# =====================================================================

# 设置默认值
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="main.py"  # 主入口文件
DEFAULT_TOKEN="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"  # 设置您的默认GitHub Token
DEFAULT_OWNER="google"
DEFAULT_REPO="benchmark"
LOG_FILE="github_analyzer_$(date +%Y%m%d_%H%M%S).log"
REPO_LIST_FILE=""
DATA_DIR="github_data"

# 全量数据获取设置（0表示无限制）
DEFAULT_COMMITS=0
DEFAULT_ISSUES=0
DEFAULT_PRS=0
DEFAULT_CONTRIBUTORS=0
DEFAULT_STARS=0
DEFAULT_EVENT_PAGES=100
DEFAULT_ACTIVITY_DAYS=3650
DEFAULT_DIRECT_PUSH_DAYS=3650

# ANSI颜色代码
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
    echo -e "${BLUE}GitHub仓库数据分析工具${NC}"
    echo
    echo "使用方法:"
    echo "  $0 [选项]"
    echo
    echo "选项:"
    echo "  -h, --help                 显示此帮助信息"
    echo "  -t, --token TOKEN          GitHub API 访问令牌 (必需)"
    echo "  -o, --owner OWNER          仓库所有者 (默认: $DEFAULT_OWNER)"
    echo "  -r, --repo REPO            仓库名称 (默认: $DEFAULT_REPO)"
    echo "  -l, --list FILE            包含仓库列表的文件 (格式: owner/repo，每行一个)"
    echo "  -d, --data-dir DIR         数据存储目录 (默认: $DATA_DIR)"
    echo "  --log FILE                 日志文件 (默认: $LOG_FILE)"
    echo
    echo "功能选择 (默认获取全部数据):"
    echo "  --all                      收集所有数据"
    echo "  --overview                 仅获取仓库概览"
    echo "  --commits-only             仅获取提交历史"
    echo "  --activity-only            仅获取活动摘要"
    echo "  --pr-only                  仅获取PR"
    echo "  --issues-only              仅获取问题"
    echo "  --contributors-only        仅获取贡献者"
    echo "  --branches-only            仅获取分支信息"
    echo "  --events-only              仅获取事件历史"
    echo
    echo "数据收集参数 (默认全量获取):"
    echo "  --commits N                收集的最大提交数 (默认: 无限制)"
    echo "  --issues N                 收集的最大问题数 (默认: 无限制)"
    echo "  --prs N                    收集的最大PR数 (默认: 无限制)"
    echo "  --contributors N           收集的最大贡献者数 (默认: 无限制)"
    echo "  --stars N                  收集的最大Star用户数 (默认: 无限制)"
    echo "  --event-pages N            事件页数获取量 (默认: 10)"
    echo "  --activity-days N          活动分析时间范围（天） (默认: 180)"
    echo "  --direct-push-days N       直接推送分析时间范围（天） (默认: 90)"
    echo
    echo "示例:"
    echo "  $0 -t YOUR_TOKEN -o microsoft -r vscode"
    echo "  $0 -t YOUR_TOKEN -l popular_repos.txt"
    echo "  $0 -t YOUR_TOKEN -o apache -r kafka --activity-only"
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

# 验证Python环境
check_python() {
    if ! command -v python3 &> /dev/null; then
        log "ERROR" "未找到python3命令，请安装Python 3"
        exit 1
    fi
    
    # 检查必要的Python库
    python3 -c "import requests, json" 2>/dev/null
    if [ $? -ne 0 ]; then
        log "ERROR" "缺少必要的Python库，请运行: pip install requests"
        exit 1
    fi
}

# 解析仓库列表文件
parse_repo_list() {
    local file=$1
    if [ ! -f "$file" ]; then
        log "ERROR" "仓库列表文件不存在: $file"
        exit 1
    fi
    
    # 确保文件内容有效
    local count=$(grep -c -E '^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$' "$file")
    if [ $count -eq 0 ]; then
        log "ERROR" "仓库列表文件格式无效，应为每行一个 'owner/repo' 格式的仓库"
        exit 1
    fi
    
    log "INFO" "从文件加载了 $count 个仓库"
}

# 分析单个仓库
analyze_repo() {
    local owner=$1
    local repo=$2
    local token=$3
    local cmd_args=$4
    
    log "INFO" "开始分析仓库: $owner/$repo"
    
    # 构建并执行命令
    local cmd="python3 $PYTHON_SCRIPT --token $token --owner $owner --repo $repo --data-dir $DATA_DIR $cmd_args"
    log "INFO" "执行命令: $cmd"
    
    # 执行命令并记录输出
    $cmd 2>&1 | tee -a "$LOG_FILE"
    local status=${PIPESTATUS[0]}
    
    if [ $status -eq 0 ]; then
        log "INFO" "仓库 $owner/$repo 分析完成"
    else
        log "ERROR" "仓库 $owner/$repo 分析失败，退出代码 $status"
    fi
    
    return $status
}

# 批量分析多个仓库
batch_analyze() {
    local file=$1
    local token=$2
    local cmd_args=$3
    local success=0
    local failed=0
    
    log "INFO" "开始批量分析仓库，列表文件: $file"
    
    while IFS= read -r line; do
        # 跳过空行和注释
        [[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^# ]] && continue
        
        # 解析owner/repo格式
        IFS='/' read -r owner repo <<< "$line"
        
        # 分析仓库
        analyze_repo "$owner" "$repo" "$token" "$cmd_args"
        if [ $? -eq 0 ]; then
            ((success++))
        else
            ((failed++))
            log "WARNING" "仓库 $owner/$repo 分析失败，继续下一个"
        fi
        
        # 短暂暂停，避免API速率限制问题
        sleep 2
    done < "$file"
    
    log "INFO" "批量分析完成。成功: $success, 失败: $failed"
}

# =========================
# 主程序
# =========================

# 解析命令行参数
OWNER="$DEFAULT_OWNER"
REPO="$DEFAULT_REPO"
COMMITS="$DEFAULT_COMMITS"
ISSUES="$DEFAULT_ISSUES"
PRS="$DEFAULT_PRS"
CONTRIBUTORS="$DEFAULT_CONTRIBUTORS"
STARS="$DEFAULT_STARS"
EVENT_PAGES="$DEFAULT_EVENT_PAGES"
ACTIVITY_DAYS="$DEFAULT_ACTIVITY_DAYS"
DIRECT_PUSH_DAYS="$DEFAULT_DIRECT_PUSH_DAYS"
USE_ALL=true
TOKEN="$DEFAULT_TOKEN"

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
        -o|--owner)
            OWNER="$2"
            shift 2
            ;;
        -r|--repo)
            REPO="$2"
            shift 2
            ;;
        -l|--list)
            REPO_LIST_FILE="$2"
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
        --commits)
            COMMITS="$2"
            shift 2
            ;;
        --issues)
            ISSUES="$2"
            shift 2
            ;;
        --prs)
            PRS="$2"
            shift 2
            ;;
        --contributors)
            CONTRIBUTORS="$2"
            shift 2
            ;;
        --stars)
            STARS="$2"
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
        --all)
            USE_ALL=true
            shift
            ;;
        --overview)
            OVERVIEW=true
            USE_ALL=false
            shift
            ;;
        --commits-only)
            COMMITS_ONLY=true
            USE_ALL=false
            shift
            ;;
        --activity-only)
            ACTIVITY_ONLY=true
            USE_ALL=false
            shift
            ;;
        --pr-only)
            PR_ONLY=true
            USE_ALL=false
            shift
            ;;
        --issues-only)
            ISSUES_ONLY=true
            USE_ALL=false
            shift
            ;;
        --contributors-only)
            CONTRIBUTORS_ONLY=true
            USE_ALL=false
            shift
            ;;
        --branches-only)
            BRANCHES_ONLY=true
            USE_ALL=false
            shift
            ;;
        --events-only)
            EVENTS_ONLY=true
            USE_ALL=false
            shift
            ;;
        *)
            log "ERROR" "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 检查是否提供了token
if [ -z "$TOKEN" ]; then
    log "ERROR" "GitHub API 访问令牌是必需的"
    show_help
    exit 1
fi

# 检查Python环境
check_python

# 构建限制参数
CMD_ARGS=""
[ "$COMMITS" != "0" ] && CMD_ARGS="$CMD_ARGS --commits $COMMITS"
[ "$ISSUES" != "0" ] && CMD_ARGS="$CMD_ARGS --issues $ISSUES"
[ "$PRS" != "0" ] && CMD_ARGS="$CMD_ARGS --prs $PRS"
[ "$CONTRIBUTORS" != "0" ] && CMD_ARGS="$CMD_ARGS --contributors $CONTRIBUTORS"
[ "$STARS" != "0" ] && CMD_ARGS="$CMD_ARGS --stars $STARS"
CMD_ARGS="$CMD_ARGS --event-pages $EVENT_PAGES"
CMD_ARGS="$CMD_ARGS --activity-days $ACTIVITY_DAYS"
CMD_ARGS="$CMD_ARGS --direct-push-days $DIRECT_PUSH_DAYS"

# 添加功能选项
if [ "$OVERVIEW" = true ]; then
    CMD_ARGS="$CMD_ARGS --overview"
elif [ "$COMMITS_ONLY" = true ]; then
    CMD_ARGS="$CMD_ARGS --commits-only"
elif [ "$ACTIVITY_ONLY" = true ]; then
    CMD_ARGS="$CMD_ARGS --activity-only"
elif [ "$PR_ONLY" = true ]; then
    CMD_ARGS="$CMD_ARGS --pr-only"
elif [ "$ISSUES_ONLY" = true ]; then
    CMD_ARGS="$CMD_ARGS --issues-only"
elif [ "$CONTRIBUTORS_ONLY" = true ]; then
    CMD_ARGS="$CMD_ARGS --contributors-only"
elif [ "$BRANCHES_ONLY" = true ]; then
    CMD_ARGS="$CMD_ARGS --branches-only"
elif [ "$EVENTS_ONLY" = true ]; then
    CMD_ARGS="$CMD_ARGS --events-only"
elif [ "$USE_ALL" = true ]; then
    CMD_ARGS="$CMD_ARGS --all"
fi

# 启动分析
log "INFO" "GitHub仓库分析开始，时间: $(date)"

# 根据输入模式选择操作
if [ -n "$REPO_LIST_FILE" ]; then
    # 批量分析模式
    parse_repo_list "$REPO_LIST_FILE"
    batch_analyze "$REPO_LIST_FILE" "$TOKEN" "$CMD_ARGS"
else
    # 单仓库分析模式
    analyze_repo "$OWNER" "$REPO" "$TOKEN" "$CMD_ARGS"
fi

log "INFO" "分析完成，时间: $(date)"

# 输出结果位置信息
if [ -d "$DATA_DIR" ]; then
    log "INFO" "数据已保存到目录: $DATA_DIR"
    log "INFO" "日志文件: $LOG_FILE"
fi

exit 0