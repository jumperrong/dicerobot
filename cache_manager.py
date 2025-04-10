import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CacheManager:
    """统一的缓存管理器"""
    
    def __init__(self):
        # 获取当前脚本所在目录
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        # 缓存根目录
        self.cache_root = os.path.join(self.current_dir, 'cache')
        # 创建缓存根目录
        os.makedirs(self.cache_root, exist_ok=True)
        
        # 各功能缓存目录
        self.jrrp_dir = os.path.join(self.cache_root, 'jrrp')
        self.weather_dir = os.path.join(self.cache_root, 'weather')
        
        # 创建各功能缓存目录
        for cache_dir in [self.jrrp_dir, self.weather_dir]:
            os.makedirs(cache_dir, exist_ok=True)
            
        # 各功能缓存文件路径
        self.jrrp_broadcast_file = os.path.join(self.jrrp_dir, 'broadcast_history.json')
        self.weather_broadcast_file = os.path.join(self.weather_dir, 'broadcast_history.json')
        
        logger.info("缓存管理器初始化完成")
        logger.info(f"缓存根目录: {self.cache_root}")
        
    def load_broadcast_history(self, feature: str) -> Dict[str, Any]:
        """加载指定功能的播报历史记录
        
        Args:
            feature: 功能名称 ('jrrp', 'weather')
            
        Returns:
            Dict: 播报历史记录
        """
        try:
            # 获取对应的缓存文件路径
            cache_file = getattr(self, f"{feature}_broadcast_file", None)
            if not cache_file:
                logger.error(f"未知的功能: {feature}")
                return {}
                
            # 检查缓存文件是否存在
            if not os.path.exists(cache_file):
                logger.info(f"{feature}缓存文件不存在，创建新缓存")
                return {}
                
            # 读取缓存文件
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # 检查缓存数据的日期是否是今天
            today = datetime.now().strftime('%Y-%m-%d')
            if cache_data.get('date') == today:
                logger.info(f"成功加载今日({today}){feature}缓存")
                return cache_data
            else:
                logger.info(f"缓存日期({cache_data.get('date')})不是今天({today})，已重置缓存")
                return {}
                
        except Exception as e:
            logger.error(f"加载{feature}缓存出错: {e}", exc_info=True)
            return {}
            
    def save_broadcast_history(self, feature: str, data: Dict[str, Any]) -> bool:
        """保存指定功能的播报历史记录
        
        Args:
            feature: 功能名称 ('jrrp', 'weather')
            
        Returns:
            bool: 是否保存成功
        """
        try:
            # 获取对应的缓存文件路径
            cache_file = getattr(self, f"{feature}_broadcast_file", None)
            if not cache_file:
                logger.error(f"未知的功能: {feature}")
                return False
                
            # 确保缓存目录存在
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            
            # 添加日期信息
            cache_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                **data
            }
            
            # 保存缓存文件
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"已保存{feature}缓存")
            return True
            
        except Exception as e:
            logger.error(f"保存{feature}缓存出错: {e}", exc_info=True)
            return False
            
    def get_image_cache_dir(self, feature: str) -> Optional[str]:
        """获取指定功能的图片缓存目录
        
        Args:
            feature: 功能名称 ('jrrp', 'weather')
            
        Returns:
            str: 图片缓存目录路径
        """
        try:
            # 获取对应的缓存目录
            cache_dir = getattr(self, f"{feature}_dir", None)
            if not cache_dir:
                logger.error(f"未知的功能: {feature}")
                return None
                
            # 图片缓存目录
            image_dir = os.path.join(cache_dir, 'images')
            os.makedirs(image_dir, exist_ok=True)
            
            return image_dir
            
        except Exception as e:
            logger.error(f"获取{feature}图片缓存目录出错: {e}", exc_info=True)
            return None
            
    def cleanup_old_files(self, feature: str, days: int = 7) -> None:
        """清理指定功能的过期缓存文件
        
        Args:
            feature: 功能名称 ('jrrp', 'weather')
            days: 过期天数
        """
        try:
            # 获取图片缓存目录
            image_dir = self.get_image_cache_dir(feature)
            if not image_dir:
                return
                
            # 获取当前时间
            now = datetime.now()
            # 计算过期时间点
            expiry_date = now - timedelta(days=days)
            
            # 遍历图片缓存目录中的所有文件
            removed_count = 0
            for filename in os.listdir(image_dir):
                # 获取文件的完整路径
                file_path = os.path.join(image_dir, filename)
                
                try:
                    # 获取文件修改时间
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    # 检查文件是否过期
                    if file_time < expiry_date:
                        # 删除过期文件
                        os.remove(file_path)
                        removed_count += 1
                        logger.debug(f"已删除过期缓存文件: {filename}")
                except Exception as e:
                    logger.error(f"处理文件时出错: {filename}, 错误: {e}")
                    continue
                    
            if removed_count > 0:
                logger.info(f"已清理 {removed_count} 个过期缓存文件 (超过 {days} 天)")
                
        except Exception as e:
            logger.error(f"清理{feature}缓存文件出错: {e}", exc_info=True)

# 创建全局缓存管理器实例
cache_manager = CacheManager() 