#!/usr/bin/env python3
"""
GitHub 多仓库并发分析工具
支持多线程同时分析多个 GitHub 仓库的活动状态
"""

import argparse
import sys
import os
import time
import concurrent.futures
import threading
import queue
import json
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime

# 导入自定义模块
from github_repo_analyzer import GitHubRepoAnalyzer
from github_api_client import GitHubGraphQLClient, GitHubRESTClient
from data_storage import DataStorage

# 创建线程锁，用于保护打印输出
print_lock = threading.Lock()

# 创建安全的打印函数
def safe_print(*args, **kwargs):
    """线程安全的打印函数"""
    with print_lock:
        print(*args, **kwargs)

class MultiRepoAnalyzer:
    """多仓库并发分析器"""
    
    def __init__(self, token: str, data_dir: str = "github_data", max_workers: int = 3):
        """初始化多仓库分析器
        
        Args:
            token: GitHub API 访问令牌
            data_dir: 数据存储目录
            max_workers: 最大工作线程数
        """
        self.token = token
        self.data_dir = data_dir
        self.max_workers = max_workers
        self.results = {}
        self.start_time = None
        self.end_time = None
        
        # 确保数据目录存在
        os.makedirs(data_dir, exist_ok=True)
        
        # 创建结果目录
        self.results_dir = os.path.join(data_dir, f"multi_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(self.results_dir, exist_ok=True)
        
        # 初始化结果记录文件
        self.summary_file = os.path.join(self.results_dir, "analysis_summary.json")
        
        safe_print(f"初始化多仓库分析器，最大并发数: {max_workers}")
        safe_print(f"结果将保存到: {self.results_dir}")
    
    def analyze_single_repo(self, repo_info: Dict[str, Any], limits: Dict[str, int]) -> Dict[str, Any]:
        """分析单个仓库的任务函数
        
        Args:
            repo_info: 仓库信息字典，包含owner和repo
            limits: 数据收集限制
            
        Returns:
            分析结果摘要
        """
        owner = repo_info["owner"]
        repo = repo_info["repo"]
        
        try:
            thread_id = threading.get_ident()
            safe_print(f"线程 {thread_id}: 开始分析仓库 {owner}/{repo}")
            start_time = datetime.now()
            
            # 创建仓库分析器实例
            analyzer = GitHubRepoAnalyzer(
                token=self.token,
                owner=owner,
                repo=repo,
                data_dir=self.data_dir
            )
            
            # 根据分析类型执行相应操作
            analysis_type = repo_info.get("analysis_type", "all")
            result = None
            
            if analysis_type == "overview":
                safe_print(f"线程 {thread_id}: 获取仓库 {owner}/{repo} 概览")
                result = analyzer.get_repo_overview()
            elif analysis_type == "commits":
                max_commits = limits.get("commits", None)
                safe_print(f"线程 {thread_id}: 获取仓库 {owner}/{repo} 提交历史 (最大 {max_commits or '无限制'} 条)")
                result = analyzer.get_commit_history(max_items=max_commits)
            elif analysis_type == "activity":
                days = limits.get("activity_days", 90)
                safe_print(f"线程 {thread_id}: 获取仓库 {owner}/{repo} 最近 {days} 天活动摘要")
                result = analyzer.get_repo_activity_summary(since_days=days)
            elif analysis_type == "all":
                safe_print(f"线程 {thread_id}: 收集仓库 {owner}/{repo} 所有数据")
                result = analyzer.collect_all_data(max_items_per_category=limits)
            else:
                safe_print(f"线程 {thread_id}: 未知的分析类型 {analysis_type}，默认收集所有数据")
                result = analyzer.collect_all_data(max_items_per_category=limits)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 准备结果摘要
            summary = {
                "owner": owner,
                "repo": repo,
                "analysis_type": analysis_type,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "status": "success",
                "data_dir": f"{self.data_dir}/{owner}_{repo}",
            }
            
            safe_print(f"线程 {thread_id}: 完成分析仓库 {owner}/{repo}，耗时 {duration:.2f} 秒")
            return summary
            
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds() if start_time else 0
            
            # 记录错误信息
            error_summary = {
                "owner": owner,
                "repo": repo,
                "analysis_type": repo_info.get("analysis_type", "all"),
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "status": "error",
                "error": str(e),
            }
            
            safe_print(f"线程 {thread_id}: 分析仓库 {owner}/{repo} 时出错: {str(e)}")
            return error_summary
    
    def analyze_repos(self, repo_list: List[Dict[str, Any]], limits: Dict[str, int]) -> Dict[str, Any]:
        """并发分析多个仓库
        
        Args:
            repo_list: 仓库信息列表，每个元素包含owner和repo
            limits: 数据收集限制
            
        Returns:
            分析结果摘要
        """
        self.start_time = datetime.now()
        safe_print(f"开始多仓库分析，共 {len(repo_list)} 个仓库，最大并发数 {self.max_workers}")
        
        results = []
        active_threads = []
        
        # 使用线程池执行器
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_repo = {
                executor.submit(self.analyze_single_repo, repo, limits): repo 
                for repo in repo_list
            }
            
            # 实时获取结果
            for future in concurrent.futures.as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # 实时更新结果文件
                    self._update_summary_file(results)
                    
                except Exception as exc:
                    safe_print(f"处理仓库 {repo['owner']}/{repo['repo']} 时发生异常: {exc}")
                    results.append({
                        "owner": repo["owner"],
                        "repo": repo["repo"],
                        "status": "error",
                        "error": str(exc),
                    })
        
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        
        # 准备最终汇总报告
        summary = {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "total_duration_seconds": duration,
            "total_repos": len(repo_list),
            "successful_repos": len([r for r in results if r.get("status") == "success"]),
            "failed_repos": len([r for r in results if r.get("status") == "error"]),
            "repo_results": results,
        }
        
        # 保存最终结果
        self.results = summary
        self._save_final_results()
        
        safe_print(f"多仓库分析完成，总耗时 {duration:.2f} 秒")
        safe_print(f"成功: {summary['successful_repos']}，失败: {summary['failed_repos']}")
        safe_print(f"详细结果已保存到: {self.summary_file}")
        
        return summary
    
    def _update_summary_file(self, results: List[Dict[str, Any]]) -> None:
        """更新结果摘要文件，实时记录分析进度
        
        Args:
            results: 当前所有结果列表
        """
        current_time = datetime.now()
        duration = (current_time - self.start_time).total_seconds() if self.start_time else 0
        
        summary = {
            "last_updated": current_time.isoformat(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "duration_so_far": duration,
            "completed_repos": len(results),
            "successful_repos": len([r for r in results if r.get("status") == "success"]),
            "failed_repos": len([r for r in results if r.get("status") == "error"]),
            "repo_results": results,
        }
        
        with open(self.summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    
    def _save_final_results(self) -> None:
        """保存最终分析结果"""
        if not self.results:
            return
            
        with open(self.summary_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        
        # 创建一个状态文件，标记分析完成
        status_file = os.path.join(self.results_dir, "analysis_complete.txt")
        with open(status_file, 'w', encoding='utf-8') as f:
            f.write(f"Analysis completed at: {datetime.now().isoformat()}\n")
            f.write(f"Total duration: {self.results['total_duration_seconds']:.2f} seconds\n")
            f.write(f"Analyzed repos: {self.results['total_repos']}\n")
            f.write(f"Successful: {self.results['successful_repos']}\n")
            f.write(f"Failed: {self.results['failed_repos']}\n")


def parse_repo_list_file(file_path: str) -> List[Dict[str, Any]]:
    """解析仓库列表文件
    
    文件格式: 每行一个仓库，格式为 owner/repo 或 owner/repo:analysis_type
    
    Args:
        file_path: 仓库列表文件路径
        
    Returns:
        仓库信息列表
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"仓库列表文件不存在: {file_path}")
    
    repo_list = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
                
            # 检查是否包含分析类型
            if ':' in line:
                repo_path, analysis_type = line.split(':', 1)
                analysis_type = analysis_type.strip()
            else:
                repo_path = line
                analysis_type = "all"  # 默认为全量分析
                
            # 解析 owner/repo 格式
            try:
                owner, repo = repo_path.split('/', 1)
                repo_list.append({
                    "owner": owner.strip(),
                    "repo": repo.strip(),
                    "analysis_type": analysis_type
                })
            except ValueError:
                safe_print(f"警告: 忽略格式不正确的仓库路径: {line}")
                continue
    
    return repo_list


def main():
    """主函数，解析命令行参数并执行多仓库分析"""
    parser = argparse.ArgumentParser(description='GitHub多仓库并发分析工具')
    
    # 必需参数
    parser.add_argument('--token', type=str, help='GitHub API 访问令牌', required=True)
    
    # 仓库相关参数 - 支持单仓库或仓库列表文件
    repo_group = parser.add_mutually_exclusive_group(required=True)
    repo_group.add_argument('--repo-list', type=str, help='包含仓库列表的文件路径')
    repo_group.add_argument('--owner-repo', type=str, help='单个仓库，格式为 owner/repo')
    
    # 数据存储
    parser.add_argument('--data-dir', type=str, default='github_data', 
                      help='数据存储目录，默认为 "github_data"')
    
    # 并行处理参数
    parser.add_argument('--workers', type=int, default=3, 
                      help='最大工作线程数，默认为 3')
    
    # 数据收集限制
    parser.add_argument('--commits', type=int, default=500, help='最大提交获取数量，默认 500')
    parser.add_argument('--issues', type=int, default=200, help='最大问题获取数量，默认 200')
    parser.add_argument('--prs', type=int, default=200, help='最大PR获取数量，默认 200')
    parser.add_argument('--contributors', type=int, default=100, help='最大贡献者获取数量，默认 100')
    parser.add_argument('--stars', type=int, default=100, help='最大Star用户获取数量，默认 100')
    parser.add_argument('--event-pages', type=int, default=5, help='事件页数获取量，默认 5 页')
    parser.add_argument('--activity-days', type=int, default=90, 
                      help='活动分析时间范围（天数），默认 90 天')
    parser.add_argument('--direct-push-days', type=int, default=30, 
                      help='直接推送分析时间范围（天数），默认 30 天')
    
    # 分析类型
    parser.add_argument('--analysis-type', type=str, default='all', 
                      choices=['all', 'overview', 'commits', 'activity'],
                      help='分析类型，默认为 all')
    
    args = parser.parse_args()
    
    # 构建限制字典
    limits = {
        "commits": args.commits,
        "issues": args.issues,
        "pull_requests": args.prs,
        "contributors": args.contributors,
        "stargazers": args.stars,
        "event_pages": args.event_pages,
        "days_for_activities": args.activity_days,
        "activity_period": args.activity_days,
        "days_for_direct_push": args.direct_push_days
    }
    
    # 准备仓库列表
    if args.repo_list:
        try:
            repo_list = parse_repo_list_file(args.repo_list)
            if not repo_list:
                safe_print("错误: 仓库列表为空")
                sys.exit(1)
            safe_print(f"从文件加载了 {len(repo_list)} 个仓库")
        except Exception as e:
            safe_print(f"解析仓库列表文件时出错: {str(e)}")
            sys.exit(1)
    else:  # 单个仓库
        try:
            owner, repo = args.owner_repo.split('/', 1)
            repo_list = [{
                "owner": owner.strip(),
                "repo": repo.strip(),
                "analysis_type": args.analysis_type
            }]
            safe_print(f"将分析单个仓库: {owner}/{repo}")
        except ValueError:
            safe_print(f"错误: 仓库格式不正确，应为 owner/repo: {args.owner_repo}")
            sys.exit(1)
    
    # 创建并执行多仓库分析
    analyzer = MultiRepoAnalyzer(
        token=args.token,
        data_dir=args.data_dir,
        max_workers=args.workers
    )
    
    try:
        results = analyzer.analyze_repos(repo_list, limits)
        
        # 输出汇总信息
        safe_print("\n===== 分析完成 =====")
        safe_print(f"总仓库数: {results['total_repos']}")
        safe_print(f"成功数: {results['successful_repos']}")
        safe_print(f"失败数: {results['failed_repos']}")
        safe_print(f"总耗时: {results['total_duration_seconds']:.2f} 秒")
        safe_print(f"详细结果已保存到: {analyzer.summary_file}")
        
        # 如果有失败的仓库，输出失败列表
        if results['failed_repos'] > 0:
            safe_print("\n失败的仓库:")
            for repo_result in results['repo_results']:
                if repo_result.get('status') == 'error':
                    safe_print(f"  - {repo_result['owner']}/{repo_result['repo']}: {repo_result.get('error', '未知错误')}")
        
        return 0
    except KeyboardInterrupt:
        safe_print("\n用户中断，正在终止分析...")
        return 1
    except Exception as e:
        safe_print(f"分析过程中发生错误: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())