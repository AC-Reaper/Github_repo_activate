"""
数据存储模块
处理 GitHub 仓库分析数据的存储和加载
"""

import os
import json
from datetime import datetime
from typing import Any, List

class DataStorage:
    """数据存储处理类"""
    
    def __init__(self, owner: str, repo: str, data_dir: str = "github_data"):
        """初始化数据存储
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            data_dir: 数据存储根目录
        """
        self.owner = owner
        self.repo = repo
        self.base_dir = os.path.join(data_dir, f"{owner}_{repo}")
        
        # 确保数据目录存在
        os.makedirs(self.base_dir, exist_ok=True)
        
        print(f"数据将存储在: {self.base_dir}")
    
    def save_data(self, data_type: str, data: Any) -> str:
        """保存数据到文件
        
        Args:
            data_type: 数据类型标识符
            data: 要保存的数据对象
            
        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{data_type}_{timestamp}.json"
        filepath = os.path.join(self.base_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
        print(f"数据已保存到: {filepath}")
        return filepath
    
    def load_data(self, data_type: str, latest: bool = True) -> Any:
        """加载保存的数据
        
        Args:
            data_type: 数据类型标识符
            latest: 是否只加载最新文件，False则加载所有匹配文件
            
        Returns:
            加载的数据对象，如果latest=False则返回对象列表
        """
        files = [f for f in os.listdir(self.base_dir) 
                if f.startswith(data_type) and f.endswith('.json')]
        
        if not files:
            print(f"未找到匹配的{data_type}数据文件")
            return None
            
        if latest:
            # 获取最新文件
            files.sort(reverse=True)
            latest_file = files[0]
            filepath = os.path.join(self.base_dir, latest_file)
            
            print(f"加载最新{data_type}数据: {latest_file}")
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 返回所有文件的数据
            result = []
            for file in sorted(files, reverse=True):
                filepath = os.path.join(self.base_dir, file)
                print(f"加载{data_type}数据: {file}")
                with open(filepath, 'r', encoding='utf-8') as f:
                    result.append(json.load(f))
            return result
    
    def list_data_files(self, data_type: str = None) -> List[str]:
        """列出所有数据文件
        
        Args:
            data_type: 可选的数据类型过滤器
            
        Returns:
            匹配的文件名列表
        """
        if data_type:
            files = [f for f in os.listdir(self.base_dir) 
                    if f.startswith(data_type) and f.endswith('.json')]
        else:
            files = [f for f in os.listdir(self.base_dir) 
                    if f.endswith('.json')]
        
        return sorted(files, reverse=True)
    
    def get_storage_info(self) -> dict:
        """获取存储统计信息
        
        Returns:
            存储统计信息字典
        """
        all_files = self.list_data_files()
        data_types = {}
        
        for file in all_files:
            # 提取数据类型
            data_type = file.split('_')[0]
            if data_type not in data_types:
                data_types[data_type] = []
            data_types[data_type].append(file)
        
        # 计算总文件大小
        total_size = 0
        for file in all_files:
            file_path = os.path.join(self.base_dir, file)
            total_size += os.path.getsize(file_path)
        
        # 转换为MB
        total_size_mb = total_size / (1024 * 1024)
        
        return {
            "repository": f"{self.owner}/{self.repo}",
            "storage_directory": self.base_dir,
            "total_files": len(all_files),
            "total_size_mb": round(total_size_mb, 2),
            "data_types": {k: len(v) for k, v in data_types.items()},
            "latest_update": max([os.path.getmtime(os.path.join(self.base_dir, f)) 
                                for f in all_files]) if all_files else None
        }