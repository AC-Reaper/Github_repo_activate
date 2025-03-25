"""
GitHub 仓库分析器
收集和分析 GitHub 仓库的各种活动数据
"""

import argparse
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
import requests

# 导入自定义模块
from github_api_client import GitHubGraphQLClient, GitHubRESTClient
from data_storage import DataStorage

class GitHubRepoAnalyzer:
	"""GitHub 仓库分析器"""
	
	# 每页最大数据量设置 (GitHub GraphQL API 最大允许值通常为100)
	MAX_PAGE_SIZE = 100
	
	def __init__(self, token: str, owner: str, repo: str, data_dir: str = "github_data"):
		"""初始化仓库分析器
		
		Args:
			token: GitHub API 访问令牌
			owner: 仓库所有者
			repo: 仓库名称
			data_dir: 数据存储目录
		"""
		self.token = token
		self.owner = owner
		self.repo = repo
		
		# 初始化 API 客户端
		self.graphql_client = GitHubGraphQLClient(token)
		self.rest_client = GitHubRESTClient(token)
		
		# 初始化数据存储
		self.storage = DataStorage(owner, repo, data_dir)

		# 数据缓存
		self.data_cache = {}  
		
		print(f"初始化 GitHub 仓库分析器: {owner}/{repo}")
	
	def paginate_query(self, query_func: Callable, data_key: str, node_key: str = None, 
				  max_items: int = None, page_size: int = None) -> List:
		"""通用分页查询逻辑，添加了额外的错误处理和恢复机制
		
		Args:
			query_func: 查询函数，接受cursor参数
			data_key: 结果数据中的键，用于提取结果
			node_key: 节点数据的键（如果不直接是edges）
			max_items: 最大获取条目数，None表示获取全部
			page_size: 每页大小
			
		Returns:
			合并后的所有节点数据列表
		"""
		all_items = []
		cursor = None
		has_next_page = True
		total_fetched = 0
		consecutive_errors = 0
		max_consecutive_errors = 3  # 最大连续错误次数
		
		# 将0视为无限制
		if max_items == 0:
			max_items = None
		
		# 如果未指定页大小，使用默认值
		if page_size is None:
			page_size = self.MAX_PAGE_SIZE
		else:
			# 调整每页大小为允许的最大值
			page_size = min(page_size, self.MAX_PAGE_SIZE)
		
		while has_next_page and (max_items is None or total_fetched < max_items):
			# 调整当前页的获取数量
			current_page_size = page_size
			if max_items is not None:
				current_page_size = min(page_size, max_items - total_fetched)
				
			# 调用查询函数获取数据
			result = query_func(cursor, current_page_size)
			
			if not result or "data" not in result:
				consecutive_errors += 1
				if consecutive_errors >= max_consecutive_errors:
					print(f"连续 {max_consecutive_errors} 次查询失败，停止分页")
					break
					
				print(f"查询未返回有效数据 ({consecutive_errors}/{max_consecutive_errors})，尝试继续...")
				
				# 如果是第一页失败，无法继续
				if cursor is None:
					print("无法获取第一页数据，停止分页")
					break
					
				# 尝试使用相同的游标再次请求，但减小页大小
				reduced_page_size = max(1, current_page_size // 2)
				if reduced_page_size < current_page_size:
					print(f"尝试减小页大小到 {reduced_page_size} 并重试...")
					current_page_size = reduced_page_size
					# 暂停一下再重试
					time.sleep(2)
					continue
				
				# 如果已经减到最小，尝试移动到下一个页面
				if has_next_page and cursor:
					print("尝试跳过当前页并获取下一页...")
					continue  # 使用当前游标，将在下个循环中重试
				else:
					print("无法恢复分页过程，停止")
					break
					
			# 重置连续错误计数
			consecutive_errors = 0
				
			# 获取实际数据位置
			data = result["data"]
			for key in data_key.split('.'):
				if key in data:
					data = data[key]
				else:
					print(f"数据键 '{key}' 不存在，停止分页")
					data = None
					break
			
			if data is None:
				break
				
			# 如果有指定node_key，先获取该键下的数据
			if node_key and node_key in data:
				data = data[node_key]
				
			# 提取节点数据和分页信息
			if "edges" in data and "pageInfo" in data:
				edges = data["edges"]
				page_info = data["pageInfo"]
				
				# 提取节点
				for edge in edges:
					if "node" in edge:
						all_items.append(edge["node"])
					else:
						all_items.append(edge)
				
				# 更新分页状态
				has_next_page = page_info.get("hasNextPage", False)
				cursor = page_info.get("endCursor")
				
				# 更新已获取数量
				total_fetched += len(edges)
				print(f"已获取 {total_fetched} 条记录...")
				
				# 如果此页数据为空但报告有下一页，可能是异常，尝试继续
				if not edges and has_next_page:
					print("警告: 当前页没有数据但报告有下一页，继续获取")
			else:
				print("数据格式不符合分页要求，停止分页")
				break
				
			# 休眠一小段时间，避免过快请求
			time.sleep(0.8)  # 增加等待时间，减轻API负担
				
		print(f"总共获取 {total_fetched} 条记录")
		return all_items	
 
	def get_repo_overview(self) -> Dict:
		"""获取仓库基本信息和统计数据，包含完整的基本仓库字段"""
		print("\n=== 获取仓库概览 ===")
		
		# 使用GraphQL获取大部分基本信息
		query = """
		query RepoOverview($owner: String!, $name: String!) {
		repository(owner: $owner, name: $name) {
			# 基本标识符
			databaseId
			id
			name
			nameWithOwner
			isPrivate
			
			# 所有者信息
			owner {
			login
			... on User {
				databaseId
				id
				name
				email
			}
			... on Organization {
				databaseId
				id
				name
				email
			}
			}
			
			# URL和描述
			url
			homepageUrl
			description
			
			# Fork信息
			isFork
			parent {
			nameWithOwner
			}
			
			# 统计数据
			stargazerCount
			watchers {
			totalCount
			}
			forkCount
			issues(states: OPEN) {
			totalCount
			}
			
			# 大小和语言
			diskUsage
			primaryLanguage {
			name
			color
			}
			languages(first: 25, orderBy: {field: SIZE, direction: DESC}) {
			edges {
				node {
				name
				color
				}
				size
			}
			totalSize
			}
			
			# 分支和功能
			defaultBranchRef {
			name
			}
			hasIssuesEnabled
			hasProjectsEnabled
			hasWikiEnabled
			hasDiscussionsEnabled
			
			# 许可证
			licenseInfo {
			name
			spdxId
			url
			}
			
			# 时间戳
			createdAt
			updatedAt
			pushedAt
			
			# 附加统计
			pullRequests(states: OPEN) {
			totalCount
			}
			releases {
			totalCount
			}
			repositoryTopics(first: 25) {
			edges {
				node {
				topic {
					name
				}
				}
			}
			}
		}
		}
		"""
		
		variables = {
			"owner": self.owner,
			"name": self.repo
		}
		
		result = self.graphql_client.execute_query(query, variables)
		overview = {}
		
		if result and "data" in result and "repository" in result["data"]:
			repo_data = result["data"]["repository"]
			
			# 处理GraphQL返回的数据
			overview = {
				"id": repo_data.get("databaseId"),
				"node_id": repo_data.get("id"),
				"name": repo_data.get("name"),
				"full_name": repo_data.get("nameWithOwner"),
				"private": repo_data.get("isPrivate"),
				"owner": {
					"login": repo_data.get("owner", {}).get("login"),
					"id": repo_data.get("owner", {}).get("databaseId"),
					"node_id": repo_data.get("owner", {}).get("id"),
					"name": repo_data.get("owner", {}).get("name"),
					"email": repo_data.get("owner", {}).get("email")
				},
				"html_url": repo_data.get("url"),
				"homepage": repo_data.get("homepageUrl"),
				"description": repo_data.get("description"),
				"fork": repo_data.get("isFork"),
				"parent": repo_data.get("parent", {}).get("nameWithOwner") if repo_data.get("parent") else None,
				"url": f"https://api.github.com/repos/{self.owner}/{self.repo}",
				"stargazers_count": repo_data.get("stargazerCount"),
				"watchers_count": repo_data.get("watchers", {}).get("totalCount"),
				"forks_count": repo_data.get("forkCount"),
				"open_issues_count": repo_data.get("issues", {}).get("totalCount"),
				"size": repo_data.get("diskUsage"),
				"language": repo_data.get("primaryLanguage", {}).get("name") if repo_data.get("primaryLanguage") else None,
				"languages": [{
					"name": edge["node"]["name"],
					"color": edge["node"]["color"],
					"size": edge["size"]
				} for edge in repo_data.get("languages", {}).get("edges", [])],
				"languages_url": f"https://api.github.com/repos/{self.owner}/{self.repo}/languages",
				"default_branch": repo_data.get("defaultBranchRef", {}).get("name") if repo_data.get("defaultBranchRef") else None,
				"has_issues": repo_data.get("hasIssuesEnabled"),
				"has_projects": repo_data.get("hasProjectsEnabled"),
				"has_wiki": repo_data.get("hasWikiEnabled"),
				"has_discussions": repo_data.get("hasDiscussionsEnabled"),
				"license": {
					"name": repo_data.get("licenseInfo", {}).get("name"),
					"spdx_id": repo_data.get("licenseInfo", {}).get("spdxId"),
					"url": repo_data.get("licenseInfo", {}).get("url")
				} if repo_data.get("licenseInfo") else None,
				"created_at": repo_data.get("createdAt"),
				"updated_at": repo_data.get("updatedAt"),
				"pushed_at": repo_data.get("pushedAt"),
				"open_pull_requests": repo_data.get("pullRequests", {}).get("totalCount"),
				"releases_count": repo_data.get("releases", {}).get("totalCount"),
				"topics": [edge["node"]["topic"]["name"] for edge in repo_data.get("repositoryTopics", {}).get("edges", [])]
			}
			
			# 使用REST API获取subscribers_count
			try:
				subscribers_endpoint = f"repos/{self.owner}/{self.repo}/subscribers"
				subscribers = self.rest_client.get_paginated_results(subscribers_endpoint, {"per_page": 100})
				if subscribers is not None:
					overview["subscribers_count"] = len(subscribers)
				else:
					overview["subscribers_count"] = 0
			except Exception as e:
				print(f"获取订阅者数量失败: {str(e)}")
				overview["subscribers_count"] = None
			
			# 获取download_count (GitHub API不直接提供，仅统计release资源下载)
			try:
				releases_endpoint = f"repos/{self.owner}/{self.repo}/releases"
				releases = self.rest_client.get_paginated_results(releases_endpoint, {"per_page": 100})
				
				total_downloads = 0
				if releases:
					for release in releases:
						assets = release.get('assets', [])
						for asset in assets:
							total_downloads += asset.get('download_count', 0)
							
				overview["download_count"] = total_downloads
				overview["download_count_note"] = "仅统计releases资源下载次数，非仓库总下载量"
			except Exception as e:
				print(f"获取下载数量失败: {str(e)}")
				overview["download_count"] = None
			
			# 获取has_downloads信息 (GraphQL可能不直接提供)
			try:
				repo_details_endpoint = f"repos/{self.owner}/{self.repo}"
				repo_details = self.rest_client.make_request(repo_details_endpoint)
				if repo_details:
					overview["has_downloads"] = repo_details.get("has_downloads", False)
				else:
					overview["has_downloads"] = False
			except Exception as e:
				print(f"获取downloads设置失败: {str(e)}")
				overview["has_downloads"] = None
			
			print("成功获取仓库概览")
			self.graphql_client.pretty_print(overview, max_depth=1)
			
			# 保存数据
			self.storage.save_data("overview", overview)
		else:
			print("获取仓库概览失败")
		
		return overview	
 
	def get_commit_history(self, max_items: int = None) -> List:
		"""获取提交历史
		
		获取仓库提交历史，包含详细的作者和提交者信息，以支持多种分析功能。
		
		Args:
			max_items: 最大获取提交数量，None或0表示获取全部
				
		Returns:
			提交历史列表
		"""
		print("\n=== 获取提交历史 ===")
		
		# 将0转换为None（表示无限制）
		if max_items == 0:
			max_items = None
		
		# 从缓存中获取数据
		if "commits" in self.data_cache:
			print("从缓存中获取提交历史数据")
			cached_commits = self.data_cache["commits"]		
			return cached_commits[:max_items] if max_items else cached_commits
		
		query = """
		query CommitHistory($owner: String!, $name: String!, $limit: Int!, $cursor: String) {
		repository(owner: $owner, name: $name) {
			defaultBranchRef {
			name
			target {
				... on Commit {
				history(first: $limit, after: $cursor) {
					pageInfo {
					hasNextPage
					endCursor
					}
					edges {
					node {
						oid
						messageHeadline
						message
						committedDate
						author {
						name
						email
						user {
							login
							name
							avatarUrl
							url
							bio
							company
							location
							createdAt
						}
						}
						committer {
						name
						email
						user {
							login
							name
							avatarUrl
						}
						}
						additions
						deletions
						changedFiles
						# 检查是否是直接推送或通过PR
						associatedPullRequests(first: 1) {
						totalCount
						nodes {
							number
						}
						}
					}
					}
				}
				}
			}
			}
		}
		}
		"""
		
		def query_func(cursor, limit):
			variables = {
				"owner": self.owner,
				"name": self.repo,
				"limit": limit,
				"cursor": cursor
			}
			return self.graphql_client.execute_query(query, variables)
		
		commits = self.paginate_query(
			query_func, 
			"repository.defaultBranchRef.target.history", 
			max_items=max_items
		)
		
		# 标记直接推送和PR推送
		for commit in commits:
			if "associatedPullRequests" in commit:
				pr_count = commit["associatedPullRequests"].get("totalCount", 0)
				commit["isDirect"] = pr_count == 0
				# 移除associatedPullRequests对象，保留已处理的信息
				if pr_count > 0 and "nodes" in commit["associatedPullRequests"] and commit["associatedPullRequests"]["nodes"]:
					commit["pullRequestNumber"] = commit["associatedPullRequests"]["nodes"][0].get("number")
				del commit["associatedPullRequests"]
		
		if commits:
			print("提交历史示例:")
			self.graphql_client.pretty_print(commits[0])
			
			# 保存数据
			self.storage.save_data("commits", commits)

			# 缓存数据
			self.data_cache["commits"] = commits
		
		return commits

	def get_branch_details(self) -> List:
		"""获取所有分支的详细信息"""
		print("\n=== 获取分支详情 ===")
  
		# 从缓存中获取数据
		if "branches" in self.data_cache:
			print("从缓存中获取分支详情数据")
			return self.data_cache["branches"]
		
		query = """
		query BranchDetails($owner: String!, $name: String!, $limit: Int!, $cursor: String) {
		  repository(owner: $owner, name: $name) {
			refs(first: $limit, after: $cursor, refPrefix: "refs/heads/") {
			  pageInfo {
				hasNextPage
				endCursor
			  }
			  edges {
				node {
				  name
				  prefix
				  target {
					... on Commit {
					  oid
					  committedDate
					  history(first: 1) {
						totalCount
					  }
					  author {
						name
						email
						user {
						  login
						}
					  }
					}
				  }
				}
			  }
			  totalCount
			}
		  }
		}
		"""
		
		def query_func(cursor, limit):
			variables = {
				"owner": self.owner,
				"name": self.repo,
				"limit": limit,
				"cursor": cursor
			}
			return self.graphql_client.execute_query(query, variables)
		
		branches = self.paginate_query(
			query_func, 
			"repository.refs"
		)
		
		if branches:
			print("分支详情示例:")
			self.graphql_client.pretty_print(branches[0])
   		
			# 保存数据
			self.storage.save_data("branches", branches)
   
			# 缓存数据
			self.data_cache["branches"] = branches
		
		return branches
	
	def get_detailed_events(self, max_pages: int = None) -> List:
		"""获取详细的仓库事件（包括分支创建、删除、强制推送等）"""
		print("\n=== 获取详细仓库事件 ===")
		
		endpoint = f"repos/{self.owner}/{self.repo}/events"
		params = {"per_page": 100}
  
		if "detailed_events" in self.data_cache:
			print("从缓存中获取详细事件数据")
			return self.data_cache["detailed_events"]
		
		events = self.rest_client.get_paginated_results(endpoint, params, max_pages)
		
		if events:
			# 分析和标记事件类型
			processed_events = []
			
			for event in events:
				processed_event = {
					"id": event.get("id"),
					"type": event.get("type"),
					"created_at": event.get("created_at"),
					"actor": {
						"login": event.get("actor", {}).get("login"),
						"id": event.get("actor", {}).get("id"),
						"avatar_url": event.get("actor", {}).get("avatar_url")
					}
				}
				
				# 处理不同类型的事件
				payload = event.get("payload", {})
				
				# 推送事件，包括直接推送和强制推送
				if event["type"] == "PushEvent":
					processed_event["ref"] = payload.get("ref", "")
					processed_event["is_force_push"] = payload.get("forced", False)
					processed_event["commits_count"] = len(payload.get("commits", []))
					processed_event["branch"] = payload.get("ref", "").replace("refs/heads/", "")
					# 提取简短的提交信息
					if "commits" in payload and payload["commits"]:
						processed_event["commits"] = [
							{
								"sha": commit.get("sha"),
								"message": commit.get("message", "").split("\n")[0],
								"author": commit.get("author", {}).get("name")
							}
							for commit in payload["commits"][:5]  # 只保留前5个提交
						]
				
				# 分支或标签创建事件
				elif event["type"] == "CreateEvent":
					processed_event["ref_type"] = payload.get("ref_type")
					processed_event["ref"] = payload.get("ref")
					processed_event["description"] = payload.get("description")
					
					if payload.get("ref_type") == "branch":
						processed_event["event_description"] = f"分支创建: {payload.get('ref')}"
				
				# 分支或标签删除事件
				elif event["type"] == "DeleteEvent":
					processed_event["ref_type"] = payload.get("ref_type")
					processed_event["ref"] = payload.get("ref")
					
					if payload.get("ref_type") == "branch":
						processed_event["event_description"] = f"分支删除: {payload.get('ref')}"
				
				# PR事件
				elif event["type"] == "PullRequestEvent":
					pr = payload.get("pull_request", {})
					processed_event["action"] = payload.get("action")
					processed_event["pr_number"] = payload.get("number")
					processed_event["pr_title"] = pr.get("title")
					processed_event["pr_state"] = pr.get("state")
					processed_event["base_branch"] = pr.get("base", {}).get("ref")
					processed_event["head_branch"] = pr.get("head", {}).get("ref")
				
				# Issue事件
				elif event["type"] == "IssuesEvent":
					issue = payload.get("issue", {})
					processed_event["action"] = payload.get("action")
					processed_event["issue_number"] = issue.get("number")
					processed_event["issue_title"] = issue.get("title")
					processed_event["issue_state"] = issue.get("state")
				
				# 添加处理后的事件
				processed_events.append(processed_event)
			
			print("详细事件示例:")
			self.graphql_client.pretty_print(processed_events[0] if processed_events else {})
			
			# 保存数据
			self.storage.save_data("detailed_events", processed_events)
			
			# 缓存数据
			self.data_cache["detailed_events"] = processed_events
			
			return processed_events
		
		return []
	
	def get_force_pushes(self, since_days: int = 90) -> List:
		"""获取强制推送历史"""
		print(f"\n=== 获取近 {since_days} 天强制推送历史 ===")
		
		# 首先获取所有详细事件
		all_events = self.get_detailed_events()
		
		# 筛选出强制推送
		since_date = datetime.now() - timedelta(days=since_days)
		since_date_str = since_date.isoformat()
		
		force_pushes = [
			event for event in all_events 
			if event.get("type") == "PushEvent" 
			and event.get("is_force_push") == True
			and event.get("created_at", "") > since_date_str
		]
		
		print(f"找到 {len(force_pushes)} 次强制推送")
		
		if force_pushes:
			# 保存数据
			self.storage.save_data("force_pushes", force_pushes)
		
		return force_pushes
	
	def get_direct_pushes(self, since_days: int = 30) -> List:
		"""获取直接提交的历史（非通过PR）"""
		print(f"\n=== 获取近 {since_days} 天直接提交历史 ===")
		
		# 获取提交历史
		commits = self.get_commit_history(max_items=0)
		
		# 筛选时间范围
		since_date = datetime.now() - timedelta(days=since_days)
		since_date_str = since_date.isoformat()
		
		# 筛选直接提交
		direct_pushes = [
			commit for commit in commits 
			if commit.get("isDirect", False) == True
			and commit.get("committedDate", "") > since_date_str
		]
		
		print(f"找到 {len(direct_pushes)} 次直接提交")
		
		if direct_pushes:
			# 保存数据
			self.storage.save_data("direct_pushes", direct_pushes)
		
		return direct_pushes
	
	def get_branch_events(self, since_days: int = 90) -> Dict:
		"""获取分支创建和删除事件"""
		print(f"\n=== 获取近 {since_days} 天分支事件 ===")
		
		# 首先获取所有详细事件
		all_events = self.get_detailed_events()
		
		# 筛选时间范围
		since_date = datetime.now() - timedelta(days=since_days)
		since_date_str = since_date.isoformat()
		
		# 筛选分支创建和删除事件
		branch_creations = [
			event for event in all_events 
			if event.get("type") == "CreateEvent" 
			and event.get("ref_type") == "branch"
			and event.get("created_at", "") > since_date_str
		]
		
		branch_deletions = [
			event for event in all_events 
			if event.get("type") == "DeleteEvent" 
			and event.get("ref_type") == "branch"
			and event.get("created_at", "") > since_date_str
		]
		
		print(f"找到 {len(branch_creations)} 次分支创建")
		print(f"找到 {len(branch_deletions)} 次分支删除")
		
		branch_events = {
			"branch_creations": branch_creations,
			"branch_deletions": branch_deletions
		}
		
		# 保存数据
		self.storage.save_data("branch_events", branch_events)
		
		return branch_events
		
	def _get_active_branches(self, commits):
		"""从提交历史中提取活跃分支"""
		# 通过PR信息提取涉及的分支
		active_branches = set()
		branch_commit_count = {}
		
		# 添加默认分支
		active_branches.add("main")  # 假设默认分支为main或master
		active_branches.add("master")
		
		# 使用REST API获取活跃分支
		endpoint = f"repos/{self.owner}/{self.repo}/branches"
		branches_data = self.rest_client.make_request(endpoint, {"per_page": 100})
		
		if branches_data and isinstance(branches_data, list):
			for branch in branches_data:
				branch_name = branch.get("name")
				if branch_name:
					active_branches.add(branch_name)
					# 检查分支最近提交
					last_commit = branch.get("commit", {})
					branch_commit_count[branch_name] = {
						"last_commit_sha": last_commit.get("sha"),
						"last_commit_date": last_commit.get("commit", {}).get("committer", {}).get("date")
					}
		
		return [{
			"name": branch,
			"last_commit": branch_commit_count.get(branch, {}).get("last_commit_date", "unknown"),
			"last_commit_sha": branch_commit_count.get(branch, {}).get("last_commit_sha", "unknown")
		} for branch in active_branches]
	
	def get_repo_activity_summary(self, since_days: int = 90) -> Dict:
		"""获取仓库活动摘要，汇总各类活动指标"""
		print(f"\n=== 获取近 {since_days} 天仓库活动摘要 ===")
		
		# 活动开始时间
		since_date = datetime.now() - timedelta(days=since_days)
		since_date_str = since_date.isoformat()
		
		# 获取各类数据
		commits = self.get_commit_history(max_items=0) 
		events = self.get_detailed_events()
		branches = self.get_branch_details()
		
		# 筛选时间范围内的数据
		recent_commits = [c for c in commits if c.get("committedDate", "") > since_date_str]
		recent_events = [e for e in events if e.get("created_at", "") > since_date_str]
		
		# 计算各类统计指标
		direct_push_count = len([c for c in recent_commits if c.get("isDirect", False)])
		force_push_events = [e for e in recent_events if e["type"] == "PushEvent" and e.get("is_force_push", False)]
		
		branch_created_events = [e for e in recent_events if e["type"] == "CreateEvent" and e.get("ref_type") == "branch"]
		branch_deleted_events = [e for e in recent_events if e["type"] == "DeleteEvent" and e.get("ref_type") == "branch"]
		
		pull_request_events = [e for e in recent_events if e["type"] == "PullRequestEvent"]
		issue_events = [e for e in recent_events if e["type"] == "IssuesEvent"]
		
		# 构建活动摘要
		activity_summary = {
			"period": f"近 {since_days} 天",
			"since_date": since_date_str,
			"commit_count": len(recent_commits),
			"direct_push_count": direct_push_count,
			"force_push_count": len(force_push_events),
			"branch_count": len(branches),
			"branch_created_count": len(branch_created_events),
			"branch_deleted_count": len(branch_deleted_events),
			"pull_request_event_count": len(pull_request_events),
			"issue_event_count": len(issue_events),
			"active_branches": self._get_active_branches(recent_commits),
			"force_pushes": [{
				"date": e.get("created_at"),
				"branch": e.get("branch"),
				"actor": e.get("actor", {}).get("login")
			} for e in force_push_events],
			"recent_branch_creations": [{
				"date": e.get("created_at"),
				"branch": e.get("ref"),
				"actor": e.get("actor", {}).get("login")
			} for e in branch_created_events[:10]]  # 只包含最近10个
		}
		
		# 保存数据
		self.storage.save_data("activity_summary", activity_summary)
		
		print("成功生成仓库活动摘要")
		self.graphql_client.pretty_print(activity_summary, max_depth=1)
		
		return activity_summary
	
	def get_issues(self, state: str = "all", max_items: int = None) -> List:
		"""获取问题列表"""
		print(f"\n=== 获取 {state} 问题 ===")
		
		states = ["OPEN", "CLOSED"] if state.upper() == "ALL" else [state.upper()]
		
		query = """
		query Issues($owner: String!, $name: String!, $states: [IssueState!], $limit: Int!, $cursor: String) {
		  repository(owner: $owner, name: $name) {
			issues(first: $limit, after: $cursor, states: $states, orderBy: {field: CREATED_AT, direction: DESC}) {
			  pageInfo {
				hasNextPage
				endCursor
			  }
			  edges {
				node {
				  number
				  title
				  createdAt
				  updatedAt
				  closedAt
				  state
				  author {
					login
				  }
				  assignees(first: 5) {
					edges {
					  node {
						login
					  }
					}
				  }
				  comments {
					totalCount
				  }
				  labels(first: 10) {
					edges {
					  node {
						name
						color
					  }
					}
				  }
				  reactions {
					totalCount
				  }
				}
			  }
			}
		  }
		}
		"""
		
		def query_func(cursor, limit):
			variables = {
				"owner": self.owner,
				"name": self.repo,
				"states": states,
				"limit": limit,
				"cursor": cursor
			}
			return self.graphql_client.execute_query(query, variables)
		
		issues = self.paginate_query(
			query_func, 
			"repository.issues", 
			max_items=max_items
		)
		
		if issues:
			print("问题示例:")
			self.graphql_client.pretty_print(issues[0])
			
			# 保存数据
			self.storage.save_data(f"issues_{state}", issues)
		
		return issues
	
	def get_pull_requests(self, state: str = "all", max_items: int = None) -> List:
		"""获取PR列表，包含详细信息并标记接受/拒绝状态
		
		Args:
			state: PR状态筛选 ("all", "open", "closed", "merged")
			max_items: 最大获取数量，None表示获取全部
			
		Returns:
			PR列表，每个PR包含完整信息和接受/拒绝状态标记
		"""
		print(f"\n=== 获取 {state} PR ===")
		
		# 确定查询状态
		states = []
		if state.upper() == "ALL":
			states = ["OPEN", "CLOSED"]
		elif state.upper() == "MERGED":
			states = ["CLOSED"]  # GraphQL无法直接过滤merged，需要后处理
		else:
			states = [state.upper()]
		
		# GraphQL查询，获取详细PR信息
		query = """
		query PullRequests($owner: String!, $name: String!, $states: [PullRequestState!], $limit: Int!, $cursor: String) {
		repository(owner: $owner, name: $name) {
			pullRequests(first: $limit, after: $cursor, states: $states, orderBy: {field: CREATED_AT, direction: DESC}) {
			pageInfo {
				hasNextPage
				endCursor
			}
			edges {
				node {
				number
				title
				body
				state
				createdAt
				updatedAt
				closedAt
				mergedAt
				isDraft
				author {
					login
					... on User {
					id
					databaseId
					avatarUrl
					}
				}
				baseRefName
				headRefName
				headRepository {
					nameWithOwner
				}
				commits(first: 1) {
					totalCount
				}
				additions
				deletions
				changedFiles
				labels(first: 10) {
					edges {
					node {
						name
						color
					}
					}
				}
				reviewDecision
				comments {
					totalCount
				}
				reviews {
					totalCount
				}
				reactions {
					totalCount
				}
				}
			}
			}
		}
		}
		"""
		
		def query_func(cursor, limit):
			variables = {
				"owner": self.owner,
				"name": self.repo,
				"states": states,
				"limit": limit,
				"cursor": cursor
			}
			return self.graphql_client.execute_query(query, variables)
		
		# 获取PR列表
		prs = self.paginate_query(
			query_func, 
			"repository.pullRequests", 
			max_items=max_items
		)
		
		# 处理接受/拒绝状态并获取closed_by信息
		repo_admins = self._get_repo_admins()
		processed_prs = []
		
		for pr in prs:
			# 基本信息处理
			pr_number = pr.get("number")
			pr_state = pr.get("state")
			pr_merged_at = pr.get("mergedAt")
			
			# 添加基本处理状态
			pr["is_merged"] = pr_merged_at is not None
			
			# 使用REST API获取closed_by信息，GraphQL API不直接提供此字段
			if pr_state == "CLOSED":
				closed_by_info = self._get_pr_closed_by(pr_number)
				pr["closed_by"] = closed_by_info
				
				# 判断接受/拒绝状态
				if pr_merged_at:
					pr["status"] = "accepted"  # 已合并，表示接受
				else:
					# 检查是否被仓库所有者或管理员关闭
					closer_login = closed_by_info.get("login") if closed_by_info else None
					if closer_login and (closer_login == self.owner or closer_login in repo_admins):
						pr["status"] = "rejected"  # 被所有者或管理员关闭但未合并，表示拒绝
					else:
						pr["status"] = "closed"  # 被其他人关闭或关闭原因不明
			else:
				# 开放状态
				pr["closed_by"] = None
				pr["status"] = "open"
			
			# 格式化标签信息
			if "labels" in pr and "edges" in pr["labels"]:
				pr["labels"] = [edge["node"] for edge in pr["labels"]["edges"]]
			
			# 添加到处理后的列表
			processed_prs.append(pr)
		
		# 如果只请求已合并PR，过滤掉未合并的
		if state.upper() == "MERGED":
			processed_prs = [pr for pr in processed_prs if pr.get("is_merged")]
		
		if processed_prs:
			print("PR 示例:")
			self.graphql_client.pretty_print(processed_prs[0])
			
			# 获取PR统计信息
			stats = self._calculate_pr_stats(processed_prs)
			print(f"PR 统计: 总数={len(processed_prs)}, 已接受={stats['accepted_count']}, 已拒绝={stats['rejected_count']}, 其他关闭={stats['other_closed_count']}, 开放={stats['open_count']}")
			
			# 保存数据
			self.storage.save_data(f"pull_requests_{state}", processed_prs)
			self.storage.save_data(f"pull_requests_{state}_stats", stats)
		
		return processed_prs

	def _get_repo_admins(self) -> List[str]:
		"""获取仓库管理员和协作者列表"""
		try:
			# 尝试获取协作者信息（需要适当权限）
			endpoint = f"repos/{self.owner}/{self.repo}/collaborators"
			params = {"affiliation": "direct", "per_page": 100}
			collaborators = self.rest_client.get_paginated_results(endpoint, params)
			
			if collaborators:
				# 筛选具有管理员权限的用户
				admins = [collab["login"] for collab in collaborators 
						if collab.get("permissions", {}).get("admin", False)]
				return admins
		except Exception as e:
			print(f"获取仓库管理员列表失败: {str(e)}")
		
		# 如果无法获取，只返回仓库所有者作为管理员
		return [self.owner]

	def _get_pr_closed_by(self, pr_number: int) -> Dict:
		"""获取关闭PR的用户信息"""
		try:
			# GitHub REST API针对PR的timeline事件
			endpoint = f"repos/{self.owner}/{self.repo}/issues/{pr_number}/timeline"
			params = {"per_page": 100}
			headers = {"Accept": "application/vnd.github.mockingbird-preview+json"}
			
			# 使用自定义headers发起请求
			url = f"{self.rest_client.base_url}/{endpoint.lstrip('/')}"
			response = requests.get(url, headers={**self.rest_client.headers, **headers}, params=params)
			
			if response.status_code == 200:
				events = response.json()
				
				# 查找关闭事件
				for event in reversed(events):  # 从最近的事件开始查找
					if event.get("event") == "closed":
						return {
							"login": event.get("actor", {}).get("login"),
							"id": event.get("actor", {}).get("id"),
							"avatar_url": event.get("actor", {}).get("avatar_url"),
							"closed_at": event.get("created_at")
						}
		except Exception as e:
			print(f"获取PR #{pr_number}关闭者信息失败: {str(e)}")
		
		# 如果无法确定，返回None
		return None

	def _calculate_pr_stats(self, prs: List[Dict]) -> Dict:
		"""计算PR统计信息"""
		stats = {
			"total_count": len(prs),
			"open_count": 0,
			"accepted_count": 0,
			"rejected_count": 0,
			"other_closed_count": 0,
			"average_commits": 0,
			"average_changed_files": 0,
			"average_additions": 0,
			"average_deletions": 0,
			"acceptance_rate": 0
		}
		
		total_commits = 0
		total_changed_files = 0
		total_additions = 0
		total_deletions = 0
		
		for pr in prs:
			# 统计状态
			status = pr.get("status")
			if status == "open":
				stats["open_count"] += 1
			elif status == "accepted":
				stats["accepted_count"] += 1
			elif status == "rejected":
				stats["rejected_count"] += 1
			elif status == "closed":
				stats["other_closed_count"] += 1
			
			# 统计数值指标
			total_commits += pr.get("commits", {}).get("totalCount", 0)
			total_changed_files += pr.get("changedFiles", 0)
			total_additions += pr.get("additions", 0)
			total_deletions += pr.get("deletions", 0)
		
		# 计算平均值
		if stats["total_count"] > 0:
			stats["average_commits"] = total_commits / stats["total_count"]
			stats["average_changed_files"] = total_changed_files / stats["total_count"]
			stats["average_additions"] = total_additions / stats["total_count"]
			stats["average_deletions"] = total_deletions / stats["total_count"]
		
		# 计算接受率
		closed_count = stats["accepted_count"] + stats["rejected_count"] + stats["other_closed_count"]
		if closed_count > 0:
			stats["acceptance_rate"] = (stats["accepted_count"] / closed_count) * 100
		
		return stats
	
	def get_contributors(self, max_items: int = None) -> List:
		"""获取贡献者列表
		
		通过分析提交历史来获取贡献者信息，利用优化后的get_commit_history方法。
		
		Args:
			max_items: 最大获取贡献者数量，None表示无限制
			
		Returns:
			贡献者列表
		"""
		print("\n=== 获取贡献者 ===")
		
		commit_history = self.get_commit_history(max_items=0)
		
		print(f"分析 {len(commit_history)} 次提交来获取贡献者信息")
		
		# 提取并统计贡献者信息
		contributor_map = {}  # 用户名 -> 用户信息
		commit_counts = {}    # 用户名 -> 提交次数
		email_map = {}        # 邮箱 -> 用户名(处理未关联GitHub账号的提交)
		
		# 处理每个提交
		for commit in commit_history:
			# 处理作者信息
			if "author" in commit and commit["author"]:
				author = commit["author"]
				self._process_contributor(author, contributor_map, commit_counts, email_map)
				
			# 处理提交者信息(可能与作者不同)
			if "committer" in commit and commit["committer"]:
				committer = commit["committer"]
				self._process_contributor(committer, contributor_map, commit_counts, email_map)
		
		# 整理贡献者列表，添加提交统计
		contributors = []
		for login, user_info in contributor_map.items():
			if login in commit_counts:
				user_info["commitCount"] = commit_counts[login]
				contributors.append(user_info)
		
		# 添加无GitHub账号但有邮箱的贡献者
		for email, name in email_map.items():
			if email not in [c.get("email") for c in contributors if "email" in c]:
				contributors.append({
					"name": name,
					"email": email,
					"commitCount": commit_counts.get(email, 0),
					"isGitHubUser": False
				})
		
		# 按提交数量排序
		contributors.sort(key=lambda x: x.get("commitCount", 0), reverse=True)
		
		# 如果指定了最大获取数量，截取相应数量
		if max_items is not None and max_items > 0:
			contributors = contributors[:max_items]
		
		if contributors:
			print(f"总共找到 {len(contributors)} 个贡献者")
			print("贡献者示例:")
			self.graphql_client.pretty_print(contributors[0])
			
			# 保存数据
			self.storage.save_data("contributors", contributors)
		else:
			print("未找到贡献者信息")
		
		return contributors

	def _process_contributor(self, person, contributor_map, commit_counts, email_map):
		"""处理贡献者信息，更新统计数据
		
		Args:
			person: 提交中的作者或提交者信息
			contributor_map: 用户名 -> 用户信息的映射
			commit_counts: 用户名/邮箱 -> 提交次数的映射
			email_map: 邮箱 -> 用户名/姓名的映射
		"""
		# 处理有GitHub账号的情况
		if "user" in person and person["user"]:
			user = person["user"]
			login = user.get("login")
			
			if login:
				# 更新提交次数
				commit_counts[login] = commit_counts.get(login, 0) + 1
				
				# 只在首次遇到此用户时添加详细信息
				if login not in contributor_map:
					contributor_map[login] = user
					contributor_map[login]["isGitHubUser"] = True
					
					# 添加邮箱信息(如果有)
					if "email" in person and person["email"]:
						contributor_map[login]["email"] = person["email"]
		
		# 处理只有邮箱的情况(无GitHub账号或未关联)
		elif "email" in person and person["email"]:
			email = person["email"]
			name = person.get("name", "Unknown")
			
			# 更新提交计数
			commit_counts[email] = commit_counts.get(email, 0) + 1
			
			# 记录邮箱与姓名的对应关系
			if email not in email_map:
				email_map[email] = name
    
	def get_stargazers(self, max_items: int = None) -> List:
		"""获取 Star 用户列表"""
		print("\n=== 获取 Star 用户 ===")
		
		query = """
		query Stargazers($owner: String!, $name: String!, $limit: Int!, $cursor: String) {
		  repository(owner: $owner, name: $name) {
			stargazers(first: $limit, after: $cursor, orderBy: {field: STARRED_AT, direction: DESC}) {
			  pageInfo {
				hasNextPage
				endCursor
			  }
			  edges {
				starredAt
				node {
				  login
				  name
				  bio
				  avatarUrl
				  company
				  location
				  createdAt
				}
			  }
			  totalCount
			}
		  }
		}
		"""
		
		def query_func(cursor, limit):
			variables = {
				"owner": self.owner,
				"name": self.repo,
				"limit": limit,
				"cursor": cursor
			}
			return self.graphql_client.execute_query(query, variables)
		
		# 检查总数，确定是否需要获取全部
		variables = {
			"owner": self.owner,
			"name": self.repo,
			"limit": 1,
			"cursor": None
		}
		result = self.graphql_client.execute_query(query, variables)
		
		total_count = 0
		if result and "data" in result and "repository" in result["data"]:
			repo = result["data"]["repository"]
			if "stargazers" in repo and "totalCount" in repo["stargazers"]:
				total_count = repo["stargazers"]["totalCount"]
				print(f"仓库总计有 {total_count} 个 Star")
		
		stargazers = self.paginate_query(
			query_func, 
			"repository.stargazers", 
			max_items=max_items
		)
		
		if stargazers:
			print("Star 用户示例:")
			self.graphql_client.pretty_print(stargazers[0])
			
			# 保存数据
			self.storage.save_data("stargazers", stargazers)
		
		return stargazers
		
	def collect_all_data(self, max_items_per_category: Optional[Dict[str, int]] = None) -> Dict:
		"""收集所有仓库数据
		
		Args:
			max_items_per_category: 每个类别的最大获取数量，为空则获取全部
			  例如：{'commits': 1000, 'issues': 500}
		
		Returns:
			包含所有数据的字典
		"""
		if max_items_per_category is None:
			max_items_per_category = {}
		
		# 将所有的0转换为None（表示无限制）
		for key in list(max_items_per_category.keys()):
			if max_items_per_category[key] == 0:
				max_items_per_category[key] = None

		
		print(f"\n===== 开始全面收集 {self.owner}/{self.repo} 仓库数据 =====")
		all_data = {}
		
		# 1. 仓库概览
		print("\n>> 步骤 1/12: 获取仓库概览")
		all_data["overview"] = self.get_repo_overview()
		
		# 2. 提交历史
		print("\n>> 步骤 2/12: 获取提交历史")
		max_commits = max_items_per_category.get("commits")
		all_data["commits"] = self.get_commit_history(max_items=max_commits)
		
		# 3. 问题
		print("\n>> 步骤 3/12: 获取问题")
		max_issues = max_items_per_category.get("issues")
		all_data["issues"] = self.get_issues(state="all", max_items=max_issues)
		
		# 4. PR
		print("\n>> 步骤 4/12: 获取PR")
		max_prs = max_items_per_category.get("pull_requests")
		all_data["pull_requests"] = self.get_pull_requests(state="all", max_items=max_prs)
		
		# 5. 贡献者
		print("\n>> 步骤 5/12: 获取贡献者")
		max_contributors = max_items_per_category.get("contributors")
		all_data["contributors"] = self.get_contributors(max_items=max_contributors)
		
		# 6. 分支详情
		print("\n>> 步骤 6/12: 获取分支详情")
		all_data["branches"] = self.get_branch_details()
		
		# 7. 详细事件
		print("\n>> 步骤 7/12: 获取详细事件")
		max_event_pages = max_items_per_category.get("event_pages", 500)  # 默认获取500页事件
		all_data["detailed_events"] = self.get_detailed_events(max_pages=max_event_pages)
		
		# 8. 强制推送
		print("\n>> 步骤 8/12: 获取强制推送记录")
		days_for_force_push = max_items_per_category.get("days_for_activities", 3650)
		all_data["force_pushes"] = self.get_force_pushes(since_days=days_for_force_push)
		
		# 9. 分支事件
		print("\n>> 步骤 9/12: 获取分支事件")
		all_data["branch_events"] = self.get_branch_events(since_days=days_for_force_push)
		
		# 10. 直接推送
		print("\n>> 步骤 10/12: 获取直接推送记录")
		days_for_direct_push = max_items_per_category.get("days_for_direct_push", 3650)
		all_data["direct_pushes"] = self.get_direct_pushes(since_days=days_for_direct_push)
		
		# 11. 活动摘要
		print("\n>> 步骤 11/12: 生成活动摘要")
		activity_period = max_items_per_category.get("activity_period", 3650)
		all_data["activity_summary"] = self.get_repo_activity_summary(since_days=activity_period)
		
		# 12. Star 用户
		print("\n>> 步骤 12/12: 获取 Star 用户")
		max_stargazers = max_items_per_category.get("stargazers", 0)
		all_data["stargazers"] = self.get_stargazers(max_items=max_stargazers)
		
		print(f"\n===== 仓库 {self.owner}/{self.repo} 数据收集完成 =====")
		
		# 保存完整数据
		self.storage.save_data("complete_data", {
			"metadata": {
				"owner": self.owner,
				"repo": self.repo,
				"collected_at": datetime.now().isoformat(),
				"category_counts": {
					"commits": len(all_data.get("commits", [])),
					"issues": len(all_data.get("issues", [])),
					"pull_requests": len(all_data.get("pull_requests", [])),
					"branches": len(all_data.get("branches", [])),
					"detailed_events": len(all_data.get("detailed_events", [])),
					"force_pushes": len(all_data.get("force_pushes", [])),
					"direct_pushes": len(all_data.get("direct_pushes", [])),
					"stargazers": len(all_data.get("stargazers", []))
				}
			},
			"overview": all_data.get("overview"),
			"activity_summary": all_data.get("activity_summary")
		})
		
		return all_data 