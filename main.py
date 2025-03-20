#!/usr/bin/env python3
"""
GitHub 仓库分析工具 - 主入口
通过命令行参数控制各种分析功能
"""

import argparse
import sys
import os
from typing import Dict, Optional

from github_repo_analyzer import GitHubRepoAnalyzer

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='GitHub仓库活动分析工具')
    
    # 必需参数
    parser.add_argument('--token', type=str, help='GitHub API 访问令牌', required=True)
    parser.add_argument('--owner', type=str, help='仓库所有者', required=True)
    parser.add_argument('--repo', type=str, help='仓库名称', required=True)
    
    # 数据存储
    parser.add_argument('--data-dir', type=str, default='github_data', 
                      help='数据存储目录，默认为 "github_data"')
    
    # 数据收集限制
    parser.add_argument('--commits', type=int, help='最大提交获取数量')
    parser.add_argument('--issues', type=int, help='最大问题获取数量')
    parser.add_argument('--prs', type=int, help='最大PR获取数量')
    parser.add_argument('--contributors', type=int, help='最大贡献者获取数量')
    parser.add_argument('--stars', type=int, help='最大Star用户获取数量')
    parser.add_argument('--event-pages', type=int, default=5, help='事件页数获取量，默认为5页')
    parser.add_argument('--activity-days', type=int, default=90, 
                      help='活动分析时间范围（天数），默认为90天')
    parser.add_argument('--direct-push-days', type=int, default=30, 
                      help='直接推送分析时间范围（天数），默认为30天')
    
    # 功能选择
    parser.add_argument('--all', action='store_true', help='收集所有数据')
    parser.add_argument('--overview', action='store_true', help='仅获取仓库概览')
    parser.add_argument('--commits-only', action='store_true', help='仅获取提交历史')
    parser.add_argument('--activity-only', action='store_true', help='仅获取活动摘要')
    parser.add_argument('--pr-only', action='store_true', help='仅获取PR')
    parser.add_argument('--issues-only', action='store_true', help='仅获取问题')
    parser.add_argument('--contributors-only', action='store_true', help='仅获取贡献者')
    parser.add_argument('--branches-only', action='store_true', help='仅获取分支信息')
    parser.add_argument('--events-only', action='store_true', help='仅获取事件历史')
    
    return parser.parse_args()

def validate_token(token: str) -> bool:
    """简单验证令牌格式"""
    if not token or len(token) < 10:
        print("错误: GitHub 令牌格式不正确，请提供有效的访问令牌")
        return False
    return True

def run_analysis(args) -> None:
    """运行仓库分析"""
    print(f"准备分析 GitHub 仓库: {args.owner}/{args.repo}")
    
    # 验证令牌格式
    if not validate_token(args.token):
        sys.exit(1)
    
    # 确保数据目录存在
    os.makedirs(args.data_dir, exist_ok=True)
    
    # 实例化分析器
    analyzer = GitHubRepoAnalyzer(
        token=args.token,
        owner=args.owner,
        repo=args.repo,
        data_dir=args.data_dir
    )
    
    # 构建限制字典
    limits: Dict[str, int] = {}
    if args.commits is not None:
        limits["commits"] = args.commits
    if args.issues is not None:
        limits["issues"] = args.issues
    if args.prs is not None:
        limits["pull_requests"] = args.prs
    if args.contributors is not None:
        limits["contributors"] = args.contributors
    if args.stars is not None:
        limits["stargazers"] = args.stars
    if args.event_pages is not None:
        limits["event_pages"] = args.event_pages
    if args.activity_days is not None:
        limits["days_for_activities"] = args.activity_days
        limits["activity_period"] = args.activity_days
    if args.direct_push_days is not None:
        limits["days_for_direct_push"] = args.direct_push_days
    
    # 根据命令行选择执行相应功能
    if args.overview:
        print(f"\n执行功能: 获取仓库概览")
        analyzer.get_repo_overview()
    elif args.commits_only:
        print(f"\n执行功能: 获取提交历史")
        analyzer.get_commit_history(max_items=args.commits)
    elif args.activity_only:
        print(f"\n执行功能: 获取活动摘要")
        analyzer.get_repo_activity_summary(since_days=args.activity_days)
    elif args.pr_only:
        print(f"\n执行功能: 获取PR")
        analyzer.get_pull_requests(state="all", max_items=args.prs)
    elif args.issues_only:
        print(f"\n执行功能: 获取问题")
        analyzer.get_issues(state="all", max_items=args.issues)
    elif args.contributors_only:
        print(f"\n执行功能: 获取贡献者")
        analyzer.get_contributors(max_items=args.contributors)
    elif args.branches_only:
        print(f"\n执行功能: 获取分支信息")
        analyzer.get_branch_details()
    elif args.events_only:
        print(f"\n执行功能: 获取事件历史")
        analyzer.get_detailed_events(max_pages=args.event_pages)
    elif args.all or not any([args.overview, args.commits_only, args.activity_only, args.pr_only, 
                            args.issues_only, args.contributors_only, args.branches_only, args.events_only]):
        # 默认行为是收集所有数据
        print(f"\n执行功能: 收集所有数据")
        analyzer.collect_all_data(max_items_per_category=limits)
    
    print(f"\n分析完成! 数据已保存到 {args.data_dir}/{args.owner}_{args.repo} 目录")

if __name__ == "__main__":
    args = parse_arguments()
    run_analysis(args)