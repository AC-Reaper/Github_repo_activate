"""
GitHub API 客户端模块
提供 GraphQL 和 REST API 接口，添加了更强的错误处理和重试机制
"""

import requests
import json
import time
import random
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

class GitHubGraphQLClient:
    """GitHub GraphQL API 客户端"""
    
    def __init__(self, token: str):
        """初始化 GraphQL 客户端
        
        Args:
            token: GitHub API 访问令牌
        """
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "GitHubRepoAnalyzer"
        }
        self.url = "https://api.github.com/graphql"
        self.rate_limit_remaining = None
        self.rate_limit_reset_at = None
        
    def execute_query(self, query: str, variables: Dict[str, Any] = None, 
                     retry_count: int = 0, max_retries: int = 5) -> Dict:
        """执行 GraphQL 查询，添加了指数退避重试机制
        
        Args:
            query: GraphQL 查询字符串
            variables: 查询变量
            retry_count: 当前重试次数 (内部使用)
            max_retries: 最大重试次数
            
        Returns:
            查询结果字典
        """
        if variables is None:
            variables = {}
            
        data = {"query": query, "variables": variables}
        
        try:
            # 检查速率限制，如果剩余配额不足，等待重置
            if self.rate_limit_remaining is not None and self.rate_limit_remaining < 100:
                reset_time = datetime.fromtimestamp(self.rate_limit_reset_at)
                current_time = datetime.now()
                if reset_time > current_time:
                    wait_seconds = (reset_time - current_time).total_seconds() + 5  # 额外等待5秒
                    print(f"速率限制即将耗尽，等待 {wait_seconds:.1f} 秒后重试...")
                    time.sleep(wait_seconds)
            
            response = requests.post(self.url, headers=self.headers, json=data)
            
            # 更新速率限制信息
            self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 1000))
            self.rate_limit_reset_at = int(response.headers.get('X-RateLimit-Reset', 0))
            
            print(f"GraphQL 速率限制剩余: {self.rate_limit_remaining}")
            print(f"GraphQL 请求状态码: {response.status_code}")
            
            # 处理服务器错误 (5xx状态码)
            if response.status_code >= 500:
                if retry_count < max_retries:
                    # 指数退避策略：每次重试等待时间增加，添加随机抖动
                    wait_time = (2 ** retry_count) + random.uniform(0, 1)
                    print(f"服务器错误 ({response.status_code})，{wait_time:.1f} 秒后第 {retry_count+1} 次重试...")
                    time.sleep(wait_time)
                    return self.execute_query(query, variables, retry_count + 1, max_retries)
                else:
                    print(f"达到最大重试次数 ({max_retries})，放弃请求")
                    return None
            
            response_data = response.json()
            
            # 检查错误
            if "errors" in response_data:
                print("GraphQL 查询错误:")
                should_retry = False
                
                for error in response_data["errors"]:
                    error_message = error.get('message', 'Unknown error')
                    print(f"  - {error_message}")
                    
                    # 检查是否因为超出速率限制
                    if "rate limit exceeded" in error_message.lower():
                        reset_time = datetime.fromtimestamp(self.rate_limit_reset_at)
                        current_time = datetime.now()
                        wait_seconds = (reset_time - current_time).total_seconds() + 5
                        print(f"超出速率限制，等待 {wait_seconds:.1f} 秒后重试...")
                        time.sleep(wait_seconds)
                        # 重试当前请求
                        return self.execute_query(query, variables, retry_count, max_retries)
                    
                    # 检查是否是临时错误或超时
                    if any(keyword in error_message.lower() for keyword in 
                          ["timeout", "temporary", "try again", "something went wrong"]):
                        should_retry = True
                
                # 如果是临时错误，尝试重试
                if should_retry and retry_count < max_retries:
                    wait_time = (2 ** retry_count) + random.uniform(0, 1)
                    print(f"检测到临时错误，{wait_time:.1f} 秒后第 {retry_count+1} 次重试...")
                    time.sleep(wait_time)
                    return self.execute_query(query, variables, retry_count + 1, max_retries)
                        
                return None
            
            return response_data
            
        except requests.exceptions.RequestException as e:
            print(f"GraphQL 请求异常: {str(e)}")
            
            # 网络错误重试，使用指数退避
            if retry_count < max_retries:
                wait_time = (2 ** retry_count) + random.uniform(0, 1)
                print(f"网络错误，{wait_time:.1f} 秒后第 {retry_count+1} 次重试...")
                time.sleep(wait_time)
                return self.execute_query(query, variables, retry_count + 1, max_retries)
            else:
                print(f"达到最大重试次数 ({max_retries})，放弃请求")
                return None
    
    def pretty_print(self, data: Any, max_depth: int = 2, current_depth: int = 0) -> None:
        """美化打印数据，限制嵌套深度
        
        Args:
            data: 要打印的数据
            max_depth: 最大嵌套深度
            current_depth: 当前深度
        """
        if data is None:
            print("无数据")
            return
            
        if current_depth >= max_depth and (isinstance(data, dict) or isinstance(data, list)):
            if isinstance(data, dict):
                print(f"{{{len(data)} keys}}")
            else:
                print(f"[{len(data)} items]")
            return
            
        if isinstance(data, dict) or isinstance(data, list):
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        else:
            print(data)


class GitHubRESTClient:
    """GitHub REST API 客户端"""
    
    def __init__(self, token: str):
        """初始化 REST API 客户端
        
        Args:
            token: GitHub API 访问令牌
        """
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHubRepoAnalyzer",
            'X-GitHub-Api-Version': '2022-11-28'
        }
        self.base_url = "https://api.github.com"
        
    def make_request(self, endpoint: str, params: dict = None, 
                    retry_count: int = 0, max_retries: int = 5) -> Union[Dict, List, None]:
        """发送 GET 请求并处理结果，增强了错误处理
        
        Args:
            endpoint: API 端点路径（不包括基础 URL）
            params: 查询参数
            retry_count: 当前重试次数
            max_retries: 最大重试次数
            
        Returns:
            API 响应结果
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            
            # 检查速率限制
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining:
                print(f"REST API 速率限制剩余: {remaining}")
            
            # 输出状态码
            print(f"REST 请求状态码: {response.status_code}")
            
            # 处理服务器错误 (5xx)
            if response.status_code >= 500:
                if retry_count < max_retries:
                    wait_time = (2 ** retry_count) + random.uniform(0, 1)
                    print(f"服务器错误 ({response.status_code})，{wait_time:.1f} 秒后第 {retry_count+1} 次重试...")
                    time.sleep(wait_time)
                    return self.make_request(endpoint, params, retry_count + 1, max_retries)
                else:
                    print(f"达到最大重试次数 ({max_retries})，放弃请求")
                    return None
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 202:
                print("GitHub 正在计算统计数据，请稍后再试")
                # 对于202状态也尝试重试几次
                if retry_count < 2:  # 对202状态只重试几次
                    wait_time = 5 + random.uniform(0, 2)
                    print(f"等待GitHub计算数据，{wait_time:.1f} 秒后重试...")
                    time.sleep(wait_time)
                    return self.make_request(endpoint, params, retry_count + 1, max_retries)
                return None
            elif response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(0, reset_time - int(time.time()))
                print(f"达到 API 速率限制，请等待 {wait_time} 秒后重试")
                if wait_time > 0:
                    print(f"等待 API 速率限制重置...")
                    time.sleep(wait_time + 5)  # 额外等待5秒
                    return self.make_request(endpoint, params, retry_count, max_retries)  # 重试
                return None
            elif response.status_code == 404:
                print(f"资源未找到或无权访问: {url}")
                return None
            elif response.status_code == 429:  # Too many requests
                wait_time = int(response.headers.get('Retry-After', 60))
                print(f"请求过多 (429)，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                return self.make_request(endpoint, params, retry_count, max_retries)
            else:
                print(f"错误: {response.text}")
                
                # 对于非致命错误，尝试重试
                if retry_count < max_retries and response.status_code != 400 and response.status_code != 422:
                    wait_time = (2 ** retry_count) + random.uniform(0, 1)
                    print(f"HTTP错误 ({response.status_code})，{wait_time:.1f} 秒后第 {retry_count+1} 次重试...")
                    time.sleep(wait_time)
                    return self.make_request(endpoint, params, retry_count + 1, max_retries)
                
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"REST 请求异常: {str(e)}")
            
            # 网络错误重试，使用指数退避
            if retry_count < max_retries:
                wait_time = (2 ** retry_count) + random.uniform(0, 1)
                print(f"网络错误，{wait_time:.1f} 秒后第 {retry_count+1} 次重试...")
                time.sleep(wait_time)
                return self.make_request(endpoint, params, retry_count + 1, max_retries)
            else:
                print(f"达到最大重试次数 ({max_retries})，放弃请求")
                return None
            
    def get_paginated_results(self, endpoint: str, params: dict = None, max_pages: int = None) -> List:
        """获取分页结果
        
        Args:
            endpoint: API 端点路径
            params: 查询参数
            max_pages: 最大页数限制，None表示获取所有页
            
        Returns:
            所有页的结果合并列表
        """
        # 将0视为无限制
        if max_pages == 0:
            max_pages = None
        
        if params is None:
            params = {}
            
        # 确保 per_page 参数
        if 'per_page' not in params:
            params['per_page'] = 100
            
        all_results = []
        page = 1
        has_more = True
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while has_more and (max_pages is None or page <= max_pages):
            params['page'] = page
            response = self.make_request(endpoint, params)
            
            if not response:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"连续 {max_consecutive_errors} 次请求失败，停止分页")
                    break
                # 尝试下一页，有时某页数据可能有问题
                page += 1
                print("尝试跳过当前页获取下一页数据...")
                continue
            else:
                consecutive_errors = 0  # 重置连续错误计数
                
            if isinstance(response, list):
                if not response:  # 空列表表示没有更多结果
                    has_more = False
                else:
                    all_results.extend(response)
                    page += 1
                    print(f"已获取 {len(all_results)} 条记录...")
                    # 短暂暂停，避免触发速率限制
                    time.sleep(0.5)
            else:
                # 非列表响应（可能是单个对象或错误）
                has_more = False
                if isinstance(response, dict):
                    all_results.append(response)
                    
        print(f"总共获取 {len(all_results)} 条记录")
        return all_results