import os
import shutil
import logging
from datetime import datetime
from typing import Optional, List
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, db_path: str, backup_dir: str = None):
        """
        初始化备份管理器
        
        Args:
            db_path: 数据库文件路径
            backup_dir: 备份文件存储目录，默认为数据库所在目录的backups子目录
        """
        self.db_path = db_path
        self.db_dir = os.path.dirname(db_path)
        
        if backup_dir is None:
            backup_dir = os.path.join(self.db_dir, 'backups')
        self.backup_dir = backup_dir
        
        # 确保备份目录存在
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # 备份配置
        self.max_backups = 10  # 保留的最大备份数量
        self.backup_interval = 24 * 60 * 60  # 自动备份间隔（秒），默认24小时
        
        # 自动备份线程
        self.backup_thread = None
        self.is_running = False
        
    def create_backup(self, backup_name: Optional[str] = None) -> str:
        """
        创建数据库备份
        
        Args:
            backup_name: 备份文件名，如果不指定则使用时间戳
            
        Returns:
            str: 备份文件路径
        """
        try:
            # 生成备份文件名
            if backup_name is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_name = f'backup_{timestamp}.db'
            
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            # 复制数据库文件
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"数据库备份已创建: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"创建数据库备份失败: {e}")
            raise
    
    def restore_backup(self, backup_path: str) -> bool:
        """
        从备份文件恢复数据库
        
        Args:
            backup_path: 备份文件路径
            
        Returns:
            bool: 是否恢复成功
        """
        try:
            # 检查备份文件是否存在
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"备份文件不存在: {backup_path}")
            
            # 创建当前数据库的临时备份
            temp_backup = self.create_backup(f"temp_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            
            # 恢复备份文件
            shutil.copy2(backup_path, self.db_path)
            
            logger.info(f"数据库已从备份恢复: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"恢复数据库备份失败: {e}")
            # 如果恢复失败，尝试恢复临时备份
            if 'temp_backup' in locals():
                try:
                    shutil.copy2(temp_backup, self.db_path)
                    logger.info("已恢复临时备份")
                except Exception as e2:
                    logger.error(f"恢复临时备份失败: {e2}")
            raise
    
    def list_backups(self) -> List[str]:
        """
        列出所有备份文件
        
        Returns:
            List[str]: 备份文件路径列表
        """
        try:
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.startswith('backup_') and file.endswith('.db'):
                    backups.append(os.path.join(self.backup_dir, file))
            return sorted(backups, reverse=True)
        except Exception as e:
            logger.error(f"列出备份文件失败: {e}")
            return []
    
    def cleanup_old_backups(self):
        """清理旧的备份文件，只保留最近的N个备份"""
        try:
            backups = self.list_backups()
            if len(backups) > self.max_backups:
                for backup in backups[self.max_backups:]:
                    os.remove(backup)
                    logger.info(f"已删除旧备份: {backup}")
        except Exception as e:
            logger.error(f"清理旧备份失败: {e}")
    
    def start_auto_backup(self):
        """启动自动备份线程"""
        if self.backup_thread is not None and self.backup_thread.is_alive():
            logger.warning("自动备份线程已在运行")
            return
        
        self.is_running = True
        self.backup_thread = threading.Thread(target=self._auto_backup_loop)
        self.backup_thread.daemon = True
        self.backup_thread.start()
        logger.info("自动备份线程已启动")
    
    def stop_auto_backup(self):
        """停止自动备份线程"""
        self.is_running = False
        if self.backup_thread is not None and self.backup_thread.is_alive():
            self.backup_thread.join()
            logger.info("自动备份线程已停止")
    
    def _auto_backup_loop(self):
        """自动备份循环"""
        while self.is_running:
            try:
                self.create_backup()
                self.cleanup_old_backups()
                time.sleep(self.backup_interval)
            except Exception as e:
                logger.error(f"自动备份失败: {e}")
                time.sleep(60)  # 发生错误时等待1分钟后重试 