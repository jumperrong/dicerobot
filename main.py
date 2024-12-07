import logging
import time
from queue import Empty
import yaml
import os
import json
from wcferry import Wcf
from robot import handle_message

logger = logging.getLogger(__name__)

def setup_logging(config: dict) -> None:
    """配置日志系统"""
    log_config = config.get('logging', {})
    log_file = config.get('files', {}).get('log_file', 'robot.log')
    
    logging.basicConfig(
        level=getattr(logging, log_config.get('level', 'DEBUG')),
        format=log_config.get('format', '%(asctime)s [%(levelname)s] %(message)s'),
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def load_config() -> dict:
    """加载配置文件"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"加载配置文件时出错: {e}", exc_info=True)
        return {}

def load_dnd_data(file_name: str) -> dict:
    """加载D&D数据文件"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, file_name)
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"加载D&D数据时出错: {e}", exc_info=True)
        return {}

def main():
    """主函数"""
    # 加载配置
    config = load_config()
    setup_logging(config)
    
    wcf = Wcf()
    logger.info("正在启动骰子机器人...")
    
    try:
        # 加载D&D数据
        dnd_data_file = config.get('files', {}).get('dnd_data', 'DND5E23_4_2.json')
        dnd_data = load_dnd_data(dnd_data_file)
        
        if not dnd_data:
            logger.error(f"D&D数据加载失败或为空")
        
        # 启用消息接收
        wcf.enable_receiving_msg()
        
        retry_count = 0
        max_retries = 5
        while not wcf.is_receiving_msg() and retry_count < max_retries:
            retry_count += 1
            logger.info(f"等待消息接收功能启动... ({retry_count}/{max_retries})")
            time.sleep(1)
        
        if not wcf.is_receiving_msg():
            logger.error("消息接收功能启动失败")
            return
            
        logger.info("骰子机器人已启动，开始接收消息")
        
        # 主循环
        while True:
            try:
                msg = wcf.get_msg()
                if msg:
                    handle_message(wcf, msg, config, dnd_data)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"获取消息时发生错误: {e}", exc_info=True)
                
            if not wcf.is_receiving_msg():
                logger.error("消息接收功能已断开")
                break
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在停止骰子机器人...")
    except Exception as e:
        logger.error(f"运行时发生错误: {e}", exc_info=True)
    finally:
        wcf.cleanup()
        logger.info("骰子机器人已停止")

if __name__ == "__main__":
    main() 