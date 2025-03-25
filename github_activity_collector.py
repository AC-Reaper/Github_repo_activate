#!/usr/bin/env python3
"""
TODO 
该代码尚未完善
GitHub活跃实体收集器
"""

import argparse
import csv
import json
import os
import time
import math
import random
import threading
import concurrent.futures
from datetime import datetime, timedelta
import requests
from typing import List, Dict, Set, Any, Tuple, Optional, Iterator

class RateLimiter:
    """API速率限制器"""
    
    def __init__(self, max_per_second: float = 10.0, max_per_minute: float = 50.0):
        """初始化速率限制器
        
        Args:
            max_per_second: 每秒最大请求数
            max_per_minute: 每分钟最大请求数
        """
        self.max_per_second = max_per_second
        self.max_per_minute = max_per_minute
        
        # 请求时间戳队列
        self.second_timestamps = []
        self.minute_timestamps = []
        
        # 锁，用于线程安全
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """在必要时等待以符合速率限制"""
        with self.lock:
            current_time = time.time()
            
            # 清理过期时间戳
            self.second_timestamps = [t for t in self.second_timestamps 
                                    if current_time - t < 1.0]
            self.minute_timestamps = [t for t in self.minute_timestamps 
                                    if current_time - t < 60.0]
            
            # 检查速率限制
            if len(self.second_timestamps) >= self.max_per_second:
                # 等待时间 = 最早请求时间 + 1秒 - 当前时间
                wait_time = self.second_timestamps[0] + 1.0 - current_time
                if wait_time > 0:
                    time.sleep(wait_time)
            
            if len(self.minute_timestamps) >= self.max_per_minute:
                # 等待时间 = 最早请求时间 + 60秒 - 当前时间
                wait_time = self.minute_timestamps[0] + 60.0 - current_time
                if wait_time > 0:
                    time.sleep(wait_time)
            
            # 记录本次请求时间
            current_time = time.time()  # 重新获取当前时间
            self.second_timestamps.append(current_time)
            self.minute_timestamps.append(current_time)
    
    def adjust_rates(self, remaining_hourly: int, reset_time: int):
        """根据API速率限制剩余量调整请求速率
        
        Args:
            remaining_hourly: 小时内剩余请求数
            reset_time: 速率限制重置时间戳
        """
        with self.lock:
            # 计算到重置时间还有多少秒
            seconds_to_reset = max(1, reset_time - int(time.time()))
            
            # 计算安全的请求速率(使用80%的可用配额)
            safe_rate = (remaining_hourly * 0.8) / seconds_to_reset
            
            # 调整速率，但不超过初始设置的最大值
            self.max_per_second = min(self.max_per_second, safe_rate * 2)
            self.max_per_minute = min(self.max_per_minute, safe_rate * 60)


class BatchManager:
    """批次管理器，按时间批次管理数据"""
    
    def __init__(self, output_dir: str, prefix: str = ""):
        """初始化批次管理器
        
        Args:
            output_dir: 输出目录
            prefix: 文件名前缀
        """
        self.output_dir = output_dir
        self.prefix = prefix
        
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 当前活跃批次数据
        self.active_repos = set()
        self.active_users = set()
        
        # 所有数据合集(用于检测重复)
        self.all_repos = set()
        self.all_users = set()
        
        # 批次跟踪
        self.current_batch = None
        self.completed_batches = []
    
    def set_current_batch(self, batch_info: Dict[str, Any]):
        """设置当前批次
        
        Args:
            batch_info: 批次信息字典，包含start_date和end_date
        """
        # 清空当前批次数据
        self.active_repos = set()
        self.active_users = set()
        
        # 设置批次信息
        self.current_batch = batch_info
        
        # 尝试加载已有数据
        self._load_existing_batch()
    
    def _load_existing_batch(self):
        """加载当前批次的已有数据"""
        if not self.current_batch:
            return
        
        batch_id = self._get_batch_id()
        repos_file = os.path.join(self.output_dir, f"{self.prefix}repos_{batch_id}.json")
        users_file = os.path.join(self.output_dir, f"{self.prefix}users_{batch_id}.json")
        
        if os.path.exists(repos_file):
            try:
                with open(repos_file, 'r', encoding='utf-8') as f:
                    batch_repos = set(json.load(f))
                    self.active_repos.update(batch_repos)
                    self.all_repos.update(batch_repos)
                print(f"已加载批次 {batch_id} 的 {len(batch_repos)} 个仓库")
            except Exception as e:
                print(f"加载批次仓库文件失败: {str(e)}")
        
        if os.path.exists(users_file):
            try:
                with open(users_file, 'r', encoding='utf-8') as f:
                    batch_users = set(json.load(f))
                    self.active_users.update(batch_users)
                    self.all_users.update(batch_users)
                print(f"已加载批次 {batch_id} 的 {len(batch_users)} 个用户")
            except Exception as e:
                print(f"加载批次用户文件失败: {str(e)}")
    
    def _get_batch_id(self) -> str:
        """获取当前批次的唯一ID
        
        Returns:
            批次ID字符串
        """
        if not self.current_batch:
            return "unknown"
        
        start = self.current_batch.get("start_date", "").replace("-", "")
        end = self.current_batch.get("end_date", "").replace("-", "")
        
        if start and end:
            return f"{start}_{end}"
        elif start:
            return f"{start}_onwards"
        elif end:
            return f"until_{end}"
        else:
            return "all"
    
    def add_repo(self, repo: str) -> bool:
        """添加仓库到当前批次
        
        Args:
            repo: 仓库名称(owner/repo格式)
            
        Returns:
            如果是新仓库返回True，否则False
        """
        is_new = repo not in self.all_repos
        
        if is_new:
            self.active_repos.add(repo)
            self.all_repos.add(repo)
        
        return is_new
    
    def add_user(self, user: str) -> bool:
        """添加用户到当前批次
        
        Args:
            user: 用户名
            
        Returns:
            如果是新用户返回True，否则False
        """
        is_new = user not in self.all_users
        
        if is_new:
            self.active_users.add(user)
            self.all_users.add(user)
        
        return is_new
    
    def save_current_batch(self, force: bool = False):
        """保存当前批次数据
        
        Args:
            force: 强制保存，即使数据很少
        """
        if not self.current_batch:
            print("没有活跃批次，无法保存")
            return
        
        # 如果数据太少且不强制保存，跳过
        if len(self.active_repos) < 10 and len(self.active_users) < 10 and not force:
            print(f"当前批次数据太少(仓库:{len(self.active_repos)}, 用户:{len(self.active_users)})，跳过保存")
            return
        
        batch_id = self._get_batch_id()
        
        # 保存仓库
        repos_file = os.path.join(self.output_dir, f"{self.prefix}repos_{batch_id}.json")
        with open(repos_file, 'w', encoding='utf-8') as f:
            json.dump(sorted(list(self.active_repos)), f, indent=2)
        
        # 保存用户
        users_file = os.path.join(self.output_dir, f"{self.prefix}users_{batch_id}.json")
        with open(users_file, 'w', encoding='utf-8') as f:
            json.dump(sorted(list(self.active_users)), f, indent=2)
        
        # 保存CSV格式
        repos_csv = os.path.join(self.output_dir, f"{self.prefix}repos_{batch_id}.csv")
        with open(repos_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["repository"])
            for repo in sorted(self.active_repos):
                writer.writerow([repo])
        
        users_csv = os.path.join(self.output_dir, f"{self.prefix}users_{batch_id}.csv")
        with open(users_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["username"])
            for user in sorted(self.active_users):
                writer.writerow([user])
        
        print(f"批次 {batch_id} 已保存: {len(self.active_repos)} 个仓库, {len(self.active_users)} 个用户")
        
        # 记录完成的批次
        batch_info = self.current_batch.copy()
        batch_info.update({
            "id": batch_id,
            "repos_count": len(self.active_repos),
            "users_count": len(self.active_users),
            "saved_at": datetime.now().isoformat(),
            "repos_file": repos_file,
            "users_file": users_file
        })
        
        self.completed_batches.append(batch_info)
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有批次的统计数据
        
        Returns:
            统计数据字典
        """
        return {
            "total_batches": len(self.completed_batches),
            "total_unique_repos": len(self.all_repos),
            "total_unique_users": len(self.all_users),
            "batches": self.completed_batches
        }
    
    def save_all_stats(self):
        """保存所有批次的统计数据"""
        stats = self.get_all_stats()
        
        # 生成统计文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stats_file = os.path.join(self.output_dir, f"{self.prefix}collection_stats_{timestamp}.json")
        
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        
        print(f"收集统计已保存到: {stats_file}")
        return stats_file


class GitHubActivityCollector:
    """高效收集GitHub活跃仓库和用户的收集器"""
    
    def __init__(self, token: str, output_dir: str = "github_data"):
        """初始化收集器
        
        Args:
            token: GitHub API令牌
            output_dir: 输出目录
        """
        self.token = token
        self.output_dir = output_dir
        
        # 设置API请求头
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHubActivityCollector",
            'X-GitHub-Api-Version': '2022-11-28'
        }
        
        # API基础URL
        self.api_base = "https://api.github.com"
        
        # 设置GraphQL请求头
        self.graphql_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        # GraphQL端点
        self.graphql_url = "https://api.github.com/graphql"
        
        # 速率限制器
        self.rest_limiter = RateLimiter(max_per_second=4.0, max_per_minute=30.0)
        self.search_limiter = RateLimiter(max_per_second=0.5, max_per_minute=25.0)
        self.graphql_limiter = RateLimiter(max_per_second=4.0, max_per_minute=30.0)
        
        # 创建批次管理器
        self.test_batch_manager = BatchManager(output_dir, prefix="test_")
        self.batch_manager = BatchManager(output_dir)
        
        # 统计信息
        self.stats = {
            "api_calls": 0,
            "graphql_calls": 0,
            "search_calls": 0,
            "rate_limit_hits": 0,
            "total_prs_found": 0,
            "new_repos_found": 0,
            "new_users_found": 0,
            "start_time": datetime.now().isoformat(),
        }
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 进度记录文件
        self.progress_file = os.path.join(output_dir, "collection_progress.json")
        
        # 加载进度（如果存在）
        self.progress = self._load_progress()
    
    def _make_rest_request(self, endpoint: str, params: dict = None, is_search: bool = False) -> dict:
        """发送GET请求到GitHub REST API
        
        Args:
            endpoint: API端点路径
            params: 查询参数
            is_search: 是否是搜索API请求
            
        Returns:
            API响应
        """
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        
        # 选择适当的速率限制器
        limiter = self.search_limiter if is_search else self.rest_limiter
        limiter.wait_if_needed()
        
        # 更新统计
        self.stats["api_calls"] += 1
        if is_search:
            self.stats["search_calls"] += 1
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            
            # 处理速率限制信息
            remaining = response.headers.get('X-RateLimit-Remaining')
            reset_time = response.headers.get('X-RateLimit-Reset')
            
            if remaining and reset_time:
                remaining = int(remaining)
                reset_time = int(reset_time)
                
                # 根据剩余配额调整速率
                limiter.adjust_rates(remaining, reset_time)
                
                # 当速率限制即将耗尽时提醒
                if remaining < 100:
                    print(f"警告: API速率限制即将耗尽，剩余 {remaining} 次请求")
            
            # 处理速率限制
            if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(0, reset_time - int(time.time()))
                print(f"达到API速率限制，等待 {wait_time} 秒后重试...")
                self.stats["rate_limit_hits"] += 1
                
                # 如果等待时间太长，考虑切换到另一个token或休息一段时间
                if wait_time > 600:  # 10分钟
                    print(f"等待时间过长 ({wait_time}秒)，保存当前进度")
                    self._save_progress()
                    print(f"保存完成，继续等待...")
                
                time.sleep(wait_time + 1)
                return self._make_rest_request(endpoint, params, is_search)
            
            # 处理成功响应
            if response.status_code == 200:
                return response.json()
            else:
                print(f"请求失败 ({response.status_code}): {response.text}")
                
                # 如果是404或其他客户端错误，返回空字典
                if 400 <= response.status_code < 500:
                    return {}
                
                # 如果是服务器错误，等待后重试
                print("服务器错误，5秒后重试...")
                time.sleep(5)
                return self._make_rest_request(endpoint, params, is_search)
                
        except Exception as e:
            print(f"请求异常: {str(e)}")
            print("5秒后重试...")
            time.sleep(5)
            return self._make_rest_request(endpoint, params, is_search)
    
    def _make_graphql_request(self, query: str, variables: dict = None) -> dict:
        """发送请求到GitHub GraphQL API
        
        Args:
            query: GraphQL查询
            variables: 查询变量
            
        Returns:
            API响应
        """
        if variables is None:
            variables = {}
        
        data = {"query": query, "variables": variables}
        
        # 应用速率限制
        self.graphql_limiter.wait_if_needed()
        
        # 更新统计
        self.stats["api_calls"] += 1
        self.stats["graphql_calls"] += 1
        
        try:
            response = requests.post(self.graphql_url, headers=self.graphql_headers, json=data)
            
            # 处理速率限制信息
            remaining = response.headers.get('X-RateLimit-Remaining')
            reset_time = response.headers.get('X-RateLimit-Reset')
            
            if remaining and reset_time:
                remaining = int(remaining)
                reset_time = int(reset_time)
                
                # 根据剩余配额调整速率
                self.graphql_limiter.adjust_rates(remaining, reset_time)
            
            # 处理速率限制
            if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(0, reset_time - int(time.time()))
                print(f"达到GraphQL API速率限制，等待 {wait_time} 秒后重试...")
                self.stats["rate_limit_hits"] += 1
                time.sleep(wait_time + 1)
                return self._make_graphql_request(query, variables)
            
            if response.status_code == 200:
                result = response.json()
                
                # 检查GraphQL错误
                if "errors" in result:
                    for error in result["errors"]:
                        print(f"GraphQL错误: {error['message']}")
                        
                        # 检查是否因为超出速率限制
                        if "rate limit exceeded" in error['message'].lower():
                            print("GraphQL速率限制超出，60秒后重试...")
                            self.stats["rate_limit_hits"] += 1
                            time.sleep(60)
                            return self._make_graphql_request(query, variables)
                
                return result
            else:
                print(f"GraphQL请求失败 ({response.status_code}): {response.text}")
                print("5秒后重试...")
                time.sleep(5)
                return self._make_graphql_request(query, variables)
                
        except Exception as e:
            print(f"GraphQL请求异常: {str(e)}")
            print("5秒后重试...")
            time.sleep(5)
            return self._make_graphql_request(query, variables)
    
    def _save_progress(self):
        """保存当前进度"""
        self.stats["updated_at"] = datetime.now().isoformat()
        self.stats["duration_minutes"] = (datetime.now() - datetime.fromisoformat(self.stats["start_time"])).total_seconds() / 60
        
        progress_data = {
            "stats": self.stats,
            "completed_batches": self.batch_manager.completed_batches,
            "test_completed_batches": self.test_batch_manager.completed_batches
        }
        
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, indent=2)
            
        print(f"进度已保存到: {self.progress_file}")
    
    def _load_progress(self) -> dict:
        """加载之前的进度
        
        Returns:
            进度数据字典
        """
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 更新统计信息
                    if "stats" in data:
                        # 保留开始时间，但更新其他统计
                        start_time = self.stats.get("start_time")
                        self.stats = data["stats"]
                        if start_time:
                            self.stats["start_time"] = start_time
                    
                    return data
            except Exception as e:
                print(f"加载进度文件失败: {str(e)}")
                
        return {}
    
    def _generate_time_batches(self, years: int = 5, batch_size_months: int = 1) -> List[Dict[str, str]]:
        """生成时间批次
        
        Args:
            years: 总年数
            batch_size_months: 每个批次的月数
            
        Returns:
            时间批次列表，每个元素是包含start_date和end_date的字典
        """
        # 计算总月数
        total_months = years * 12
        
        # 计算批次数
        batch_count = math.ceil(total_months / batch_size_months)
        
        # 生成批次
        batches = []
        end_date = datetime.now()
        
        for i in range(batch_count):
            batch_end = end_date - timedelta(days=i * batch_size_months * 30)
            batch_start = batch_end - timedelta(days=batch_size_months * 30)
            
            batches.append({
                "start_date": batch_start.strftime("%Y-%m-%d"),
                "end_date": batch_end.strftime("%Y-%m-%d")
            })
        
        return batches
    
    def test_sample_collection(self, days: int = 7) -> Dict[str, Any]:
        """进行样本测试收集
        
        Args:
            days: 样本天数
            
        Returns:
            测试结果字典
        """
        print(f"\n===== 开始样本收集 ({days}天) =====")
        
        # 计算样本时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        print(f"样本时间范围: {start_date_str} 至 {end_date_str}")
        
        # 设置测试批次
        test_batch = {
            "start_date": start_date_str,
            "end_date": end_date_str,
            "is_test": True
        }
        
        self.test_batch_manager.set_current_batch(test_batch)
        
        # 查询估计总数
        count_query = f"is:pr created:{start_date_str}..{end_date_str}"
        search_result = self._make_rest_request("search/issues", {"q": count_query, "per_page": 1}, is_search=True)
        
        total_count = search_result.get("total_count", 0)
        print(f"样本时间范围内的PR估计数量: {total_count}")
        
        # 收集样本数据
        sample_size = total_count  # 最多收集1000个作为样本
        print(f"开始收集 {sample_size} 个样本...")
        
        # 使用高效的GraphQL批量收集
        collected = self._collect_with_graphql(
            query = f"is:pr created:{start_date_str}..{end_date_str}",
            max_results = sample_size,
            batch_manager = self.test_batch_manager
        )
        
        if collected == 0:
            # 如果GraphQL失败，回退到REST API
            print("使用REST API收集样本...")
            self._collect_with_rest(
                query = f"is:pr created:{start_date_str}..{end_date_str}",
                max_results = sample_size,
                batch_manager = self.test_batch_manager
            )
        
        # 保存测试结果
        self.test_batch_manager.save_current_batch(force=True)
        
        # 获取语言分布
        languages = self._sample_languages(list(self.test_batch_manager.active_repos)[:50])
        
        # 分析样本结果
        print(f"\n===== 样本收集完成 =====")
        repos_count = len(self.test_batch_manager.active_repos)
        users_count = len(self.test_batch_manager.active_users)
        print(f"收集了 {repos_count} 个仓库和 {users_count} 个用户")
        print(f"常见语言: {sorted(list(languages.keys()))[:10]}")
        
        # 估算完整收集规模
        days_ratio = (5 * 365) / days
        estimated_repos = int(repos_count * days_ratio)
        estimated_users = int(users_count * days_ratio)
        
        print(f"\n===== 完整收集估算 =====")
        print(f"估计存在约 {estimated_repos} 个活跃仓库")
        print(f"估计存在约 {estimated_users} 个活跃用户")
        
        # 规划批次策略
        monthly_batches = self._generate_time_batches(years=5, batch_size_months=1)
        
        print(f"\n===== 收集策略 =====")
        print(f"将收集期分为 {len(monthly_batches)} 个月度批次")
        print(f"考虑按 {len(languages)} 种常见语言分别收集")
        
        # 构建测试结果
        test_results = {
            "sample_days": days,
            "sample_repos": repos_count,
            "sample_users": users_count,
            "sample_languages": languages,
            "monthly_batches": monthly_batches,
            "quarterly_batches": self._generate_time_batches(years=5, batch_size_months=3),
            "yearly_batches": self._generate_time_batches(years=5, batch_size_months=12),
            "estimated_repos": estimated_repos,
            "estimated_users": estimated_users,
            "stats": self.stats
        }
        
        # 保存测试结果
        test_results_file = os.path.join(self.output_dir, "test_results.json")
        with open(test_results_file, 'w', encoding='utf-8') as f:
            json.dump(test_results, f, indent=2)
        
        print(f"测试结果已保存到: {test_results_file}")
        
        return test_results
    
    def _sample_languages(self, repos: List[str], max_repos: int = 50) -> Dict[str, int]:
        """采样仓库语言
        
        Args:
            repos: 仓库列表
            max_repos: 最大采样仓库数
            
        Returns:
            语言分布字典
        """
        languages = {}
        sampled = 0
        
        for repo in repos[:max_repos]:
            if sampled >= max_repos:
                break
                
            # 获取仓库信息
            repo_info = self._make_rest_request(f"repos/{repo}")
            
            if repo_info and "language" in repo_info and repo_info["language"]:
                lang = repo_info["language"]
                languages[lang] = languages.get(lang, 0) + 1
            
            sampled += 1
        
        return languages
    
    def run_collection(self, batches: List[Dict[str, str]], 
                     use_language_filter: bool = False,
                     max_results_per_batch: int = 10000,
                     save_interval: int = 1000) -> Dict[str, Any]:
        """运行完整收集
        
        Args:
            batches: 时间批次列表
            use_language_filter: 是否使用语言过滤
            max_results_per_batch: 每个批次最大结果数
            save_interval: 保存间隔（发现多少条新数据后保存）
            
        Returns:
            收集结果统计
        """
        print(f"\n===== 开始按批次收集数据 =====")
        
        # 记录开始时间
        start_time = time.time()
        
        # 处理每个批次
        completed_batch_count = 0
        for batch in batches:
            # 检查是否已处理过这个批次
            batch_id = f"{batch['start_date']}_{batch['end_date']}"
            if any(b.get('id') == batch_id for b in self.batch_manager.completed_batches):
                print(f"批次 {batch_id} 已处理，跳过")
                completed_batch_count += 1
                continue
            
            print(f"\n处理批次: {batch['start_date']} 至 {batch['end_date']}")
            
            # 设置当前批次
            self.batch_manager.set_current_batch(batch)
            
            query = f"is:pr created:{batch['start_date']}..{batch['end_date']}"
            
            # 先尝试GraphQL批量收集
            collected = self._collect_with_graphql(
                query = query,
                max_results = max_results_per_batch,
                batch_manager = self.batch_manager,
                save_interval = save_interval
            )
            
            if collected < 100:
                # 如果GraphQL收集结果太少，尝试REST API
                print("GraphQL收集结果太少，使用REST API补充...")
                self._collect_with_rest(
                    query = query,
                    max_results = max_results_per_batch - collected,
                    batch_manager = self.batch_manager,
                    save_interval = save_interval
                )
            
            # 如果使用语言过滤，并且有大量数据，可以进一步细分
            if use_language_filter and len(self.batch_manager.active_repos) > 5000:
                print("数据量较大，按语言进一步收集...")
                # 获取常见语言
                languages = ["JavaScript", "Python", "Java", "Go", "TypeScript", "C++", "Ruby", "PHP"]
                
                for language in languages:
                    language_query = f"{query} language:{language}"
                    print(f"收集 {language} 语言的数据...")
                    
                    # 使用GraphQL收集
                    self._collect_with_graphql(
                        query = language_query,
                        max_results = 1000,  # 每种语言限制较少
                        batch_manager = self.batch_manager,
                        save_interval = save_interval
                    )
            
            # 保存当前批次
            self.batch_manager.save_current_batch(force=True)
            completed_batch_count += 1
            
            # 每完成3个批次保存一次进度
            if completed_batch_count % 3 == 0:
                self._save_progress()
        
        # 计算总耗时
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n===== 收集完成 =====")
        print(f"总耗时: {duration:.2f} 秒")
        print(f"处理了 {completed_batch_count} 个批次")
        
        # 保存最终统计
        stats_file = self.batch_manager.save_all_stats()
        
        # 保存最终进度
        self._save_progress()
        
        return {
            "duration_seconds": duration,
            "processed_batches": completed_batch_count,
            "stats": self.stats,
            "stats_file": stats_file
        }
    
    def _collect_with_graphql(self, query: str, max_results: int,
                            batch_manager: BatchManager,
                            save_interval: int = 1000) -> int:
        """使用GraphQL API收集数据
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            batch_manager: 批次管理器
            save_interval: 保存间隔
            
        Returns:
            收集的结果数
        """
        print(f"使用GraphQL收集: {query}")
        
        graphql_query = """
        query ($queryString: String!, $cursor: String) {
          search(query: $queryString, type: ISSUE, first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                ... on PullRequest {
                  repository {
                    nameWithOwner
                  }
                  author {
                    login
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {
            "queryString": query,
            "cursor": None
        }
        
        collected = 0
        new_items_since_save = 0
        has_next_page = True
        
        while has_next_page and collected < max_results:
            result = self._make_graphql_request(graphql_query, variables)
            
            if not result or "data" not in result or "search" not in result["data"]:
                print("GraphQL查询失败或返回格式不正确")
                break
            
            search_data = result["data"]["search"]
            edges = search_data.get("edges", [])
            
            if not edges:
                print("没有更多结果")
                break
            
            items_added = 0
            for edge in edges:
                node = edge.get("node", {})
                
                # 提取仓库
                if "repository" in node and "nameWithOwner" in node["repository"]:
                    repo = node["repository"]["nameWithOwner"]
                    if batch_manager.add_repo(repo):
                        self.stats["new_repos_found"] += 1
                        items_added += 1
                
                # 提取用户
                if "author" in node and node["author"] and "login" in node["author"]:
                    user = node["author"]["login"]
                    if batch_manager.add_user(user):
                        self.stats["new_users_found"] += 1
                        items_added += 1
            
            collected += len(edges)
            new_items_since_save += items_added
            
            print(f"已收集 {collected} 个结果，新增 {items_added} 个项目")
            
            # 检查是否需要保存
            if new_items_since_save >= save_interval:
                print(f"发现 {new_items_since_save} 个新项目，保存当前批次")
                batch_manager.save_current_batch()
                new_items_since_save = 0
            
            # 检查是否有下一页
            page_info = search_data.get("pageInfo", {})
            has_next_page = page_info.get("hasNextPage", False)
            
            if not has_next_page:
                print("没有下一页，收集完成")
                break
            
            # 更新游标
            variables["cursor"] = page_info.get("endCursor")
        
        print(f"GraphQL收集完成，共获取 {collected} 个结果")
        return collected
    
    def _collect_with_rest(self, query: str, max_results: int,
                         batch_manager: BatchManager,
                         save_interval: int = 1000) -> int:
        """使用REST API收集数据
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            batch_manager: 批次管理器
            save_interval: 保存间隔
            
        Returns:
            收集的结果数
        """
        print(f"使用REST API收集: {query}")
        
        params = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": 100
        }
        
        collected = 0
        new_items_since_save = 0
        page = 1
        
        while collected < max_results:
            print(f"获取第 {page} 页...")
            params["page"] = page
            
            # 执行搜索
            result = self._make_rest_request("search/issues", params, is_search=True)
            
            if not result or "items" not in result:
                print("搜索API返回无效结果")
                break
            
            items = result.get("items", [])
            if not items:
                print("没有更多结果")
                break
            
            items_added = 0
            for item in items:
                # 提取仓库
                if "repository_url" in item:
                    repo_url = item["repository_url"]
                    parts = repo_url.split("/")
                    if len(parts) >= 2:
                        repo = f"{parts[-2]}/{parts[-1]}"
                        if batch_manager.add_repo(repo):
                            self.stats["new_repos_found"] += 1
                            items_added += 1
                
                # 提取用户
                if "user" in item and "login" in item["user"]:
                    user = item["user"]["login"]
                    if batch_manager.add_user(user):
                        self.stats["new_users_found"] += 1
                        items_added += 1
            
            collected += len(items)
            new_items_since_save += items_added
            
            print(f"已收集 {collected} 个结果，新增 {items_added} 个项目")
            
            # 检查是否需要保存
            if new_items_since_save >= save_interval:
                print(f"发现 {new_items_since_save} 个新项目，保存当前批次")
                batch_manager.save_current_batch()
                new_items_since_save = 0
            
            # 检查是否已达到GitHub搜索API的限制(1000条结果)
            if page >= 10:
                print("已达到GitHub搜索API的1000条结果限制")
                break
            
            # 检查是否已获取所有结果
            if len(items) < params.get("per_page", 100):
                print("没有更多结果")
                break
            
            page += 1
        
        print(f"REST API收集完成，共获取 {collected} 个结果")
        return collected


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='优化版GitHub活跃实体收集器')
    
    parser.add_argument('--token', type=str, required=True,
                      help='GitHub API令牌')
    parser.add_argument('--output-dir', type=str, default='github_activity_data',
                      help='输出目录')
    parser.add_argument('--test-only', action='store_true',
                      help='仅运行测试样本收集')
    parser.add_argument('--sample-days', type=int, default=7,
                      help='样本收集的天数')
    parser.add_argument('--batch-size', type=int, default=1,
                      help='时间批次大小(月)')
    parser.add_argument('--use-language-filter', action='store_true',
                      help='使用语言过滤策略')
    parser.add_argument('--max-results', type=int, default=10000,
                      help='每个批次的最大结果数')
    parser.add_argument('--save-interval', type=int, default=1000,
                      help='中间保存间隔(项目数)')
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_arguments()
    
    # 创建收集器
    collector = GitHubActivityCollector(
        token=args.token,
        output_dir=args.output_dir
    )
    
    # 运行测试样本收集
    test_results = collector.test_sample_collection(days=args.sample_days)
    
    # 如果只是测试，则退出
    if args.test_only:
        print("完成测试样本收集，退出")
        return
    
    # 选择批次大小
    if args.batch_size == 1:
        batches = test_results["monthly_batches"]
        print(f"使用月度批次 ({len(batches)} 个批次)")
    elif args.batch_size == 3:
        batches = test_results["quarterly_batches"]
        print(f"使用季度批次 ({len(batches)} 个批次)")
    else:
        batches = test_results["yearly_batches"]
        print(f"使用年度批次 ({len(batches)} 个批次)")
    
    # 运行收集
    collector.run_collection(
        batches=batches,
        use_language_filter=args.use_language_filter,
        max_results_per_batch=args.max_results,
        save_interval=args.save_interval
    )

if __name__ == "__main__":
    main()