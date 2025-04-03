import os
import logging
from logging.handlers import RotatingFileHandler

class LogManager:
    """日志管理器"""
    
    def __init__(self, config: dict):
        """
        初始化日志管理器
        
        Args:
            config: 日志配置字典,包含:
                - level: 日志级别
                - format: 日志格式
                - file: 文件配置
                    - max_size: 最大文件大小(MB)
                    - path: 日志文件路径
        """
        try:
            # 获取根日志器
            root_logger = logging.getLogger()
            
            # 如果已经有处理器，说明已经初始化过，直接返回
            if root_logger.handlers:
                print("日志处理器已存在，跳过初始化")
                return
                
            # 设置根日志器的级别为 DEBUG
            root_logger.setLevel(logging.DEBUG)
            
            # 获取日志配置
            log_level = config.get('level', 'DEBUG')
            log_format = config.get('format', '%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s')
            log_file = config.get('file', {}).get('path', 'logs/robot.log')
            max_size = config.get('file', {}).get('max_size', 10) * 1024 * 1024  # 转换为字节
            
            # 确保使用绝对路径
            if not os.path.isabs(log_file):
                current_dir = os.path.dirname(os.path.abspath(__file__))
                log_file = os.path.join(current_dir, log_file)
                print(f"日志文件绝对路径: {log_file}")
                
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            try:
                if not os.path.exists(log_dir):
                    print(f"正在创建日志目录: {log_dir}")
                    os.makedirs(log_dir, exist_ok=True)
                    print(f"日志目录创建成功: {log_dir}")
                else:
                    print(f"日志目录已存在: {log_dir}")
                    
                # 检查目录权限
                if not os.access(log_dir, os.W_OK):
                    print(f"警告: 没有写入日志目录的权限: {log_dir}")
            except Exception as e:
                print(f"创建日志目录时出错: {log_dir}, 错误: {e}")
            
            # 创建格式化器
            formatter = logging.Formatter(log_format)
            
            # 创建并配置控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.DEBUG)
            
            # 添加控制台处理器
            root_logger.addHandler(console_handler)
            
            # 尝试创建文件处理器
            try:
                print(f"尝试创建日志文件处理器: {log_file}")
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=max_size,
                    backupCount=3,
                    encoding='utf-8'
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(logging.DEBUG)
                
                # 添加文件处理器
                root_logger.addHandler(file_handler)
                print(f"日志文件处理器创建成功")
                
            except Exception as e:
                print(f"创建日志文件处理器时出错: {e}")
                # 即使日志文件创建失败，也不要阻止程序运行，只使用控制台输出
                print(f"将只使用控制台记录日志")
            
            self.config = config
                
        except Exception as e:
            print(f"初始化日志管理器时出错: {e}")
    
    def check_and_clear_log(self):
        """检查并清理日志文件"""
        try:
            file_config = self.config.get('file', {})
            if not file_config:
                return
                
            # 获取日志文件的完整路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            log_path = file_config.get('path', 'logs/robot.log')
            if not os.path.isabs(log_path):
                log_path = os.path.join(current_dir, log_path)
            max_size = file_config.get('max_size', 10) * 1024 * 1024  # 转换为字节
            
            if os.path.exists(log_path):
                file_size = os.path.getsize(log_path)
                if file_size > max_size:
                    # 清空文件内容
                    try:
                        with open(log_path, 'w', encoding='utf-8') as f:
                            f.write('')
                        print(f"日志文件已超过{max_size/1024/1024}MB,已清空")
                        logging.info(f"日志文件已超过{max_size/1024/1024}MB,已清空")
                    except Exception as e:
                        print(f"清空日志文件时出错: {e}")
                        
        except Exception as e:
            print(f"检查日志文件大小时出错: {e}")
            logging.error(f"检查日志文件大小时出错: {e}") 