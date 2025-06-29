import logging
import time
from queue import Empty
import yaml
import os
import json
from wcferry import Wcf
from robot import handle_message, CommandHandler
from log_manager import LogManager
import asyncio

logger = logging.getLogger(__name__)

def load_config() -> dict:
    """加载配置文件"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 创建logs目录
        logs_dir = os.path.join(current_dir, "logs")
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            print(f"创建日志目录: {logs_dir}")  # 使用print因为logger还未初始化
        
        config_path = os.path.join(current_dir, "config.yaml")
        if not os.path.exists(config_path):
            print(f"配置文件不存在: {config_path}")  # 使用print因为logger还未初始化
            return {}
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 显示基础配置信息
        logger.info("\n=== 骰子机器人基础配置 ===")
        logger.info(f"机器人名称: {config.get('bot', {}).get('name', '未设置')}")
        logger.info(f"版本: {config.get('bot', {}).get('version', '未设置')}")
        
        # 显示日志配置
        logger.info("\n=== 日志配置 ===")
        log_file = config.get('logging', {}).get('file', {}).get('path', 'logs/robot.log')
        log_file = os.path.join(current_dir, log_file)  # 确保使用绝对路径
        logger.info(f"日志级别: {config.get('logging', {}).get('level', 'DEBUG')}")
        logger.info(f"日志文件: {log_file}")
        logger.info(f"日志大小限制: {config.get('logging', {}).get('file', {}).get('max_size', 10)}MB")
        
        # 显示AI配置
        ai_config = config.get('ai', {}).get('qwen', {})
        logger.info("\n=== AI 功能配置 ===")
        # API配置
        qwen_api_key = ai_config.get('api_key')
        if qwen_api_key and qwen_api_key != 'your_api_key_here':
            logger.info("通义千问API密钥: 已配置")
            logger.debug(f"通义千问API密钥: {qwen_api_key[:8]}...{qwen_api_key[-4:]}")
        else:
            logger.warning("通义千问API密钥未配置或无效")
        
        app_id = ai_config.get('app_id')
        if app_id:
            logger.info(f"应用ID: {app_id}")
        else:
            logger.warning("应用ID未配置")
        
        logger.info(f"模型: {ai_config.get('model', 'qwen-turbo')}")
        
        # 私聊配置
        logger.info("\n=== 私聊配置 ===")
        logger.info(f"私聊功能: {'已启用' if ai_config.get('private_chat', {}).get('enabled', False) else '已禁用'}")
        private_chat_whitelist = ai_config.get('private_chat', {}).get('whitelist', [])
        if private_chat_whitelist:
            logger.info("私聊白名单:")
            for user in private_chat_whitelist:
                logger.info(f"• {user}")
        else:
            logger.info("私聊白名单为空")
        
        # 群聊配置
        logger.info("\n=== 群聊配置 ===")
        enabled_rooms = ai_config.get('group_chat', {}).get('enabled_rooms', [])
        if enabled_rooms:
            logger.info("已启用AI功能的群聊:")
            for room_id in enabled_rooms:
                try:
                    group_name = wcf.get_room_name(room_id) or room_id
                    logger.info(f"• {group_name} ({room_id})")
                except:
                    logger.info(f"• {room_id}")
        else:
            logger.info("暂无已启用AI功能的群聊")
        
        # 天气配置
        weather_config = ai_config.get('weather', {})
        logger.info("\n=== 天气功能配置 ===")
        logger.info(f"默认城市: {weather_config.get('default_city', '未设置')}")
        
        # 天气播报配置
        daily_report = weather_config.get('daily_report', {})
        if daily_report.get('enabled', False):
            logger.info("定时播报: 已启用")
            broadcast_times = daily_report.get('broadcast_times', [])
            formatted_times = []
            for time in broadcast_times:
                if isinstance(time, int):
                    formatted_times.append(f"{time:02d}:00")
                elif isinstance(time, str):
                    try:
                        hour, minute = map(int, time.split(':'))
                        formatted_times.append(f"{hour:02d}:{minute:02d}")
                    except:
                        logger.warning(f"无效的播报时间格式: {time}")
            if formatted_times:
                logger.info(f"• 播报时间: {', '.join(formatted_times)}")
            else:
                logger.warning("• 未配置有效的播报时间")
        else:
            logger.info("定时播报: 已禁用")
        
        # 天气预警配置
        warning_config = weather_config.get('warning', {})
        if warning_config.get('enabled', False):
            logger.info("天气预警: 已启用")
            logger.info(f"• 检查间隔: {warning_config.get('interval', 10)}分钟")
        else:
            logger.info("天气预警: 已禁用")
        
        # 好友请求配置
        friend_config = config.get('friend_request', {})
        logger.info("\n=== 好友请求配置 ===")
        auto_accept = friend_config.get('auto_accept', False)
        pass_phrase = friend_config.get('pass_phrase', '')
        
        if auto_accept:
            logger.info("自动通过好友请求: 已启用")
            if pass_phrase:
                logger.info(f"• 验证口令: \"{pass_phrase}\"")
                logger.info("• 注意: 只有验证信息匹配口令时才会自动通过")
            else:
                logger.info("• 验证口令: 未设置 (将自动通过所有好友请求)")
                
            greeting = friend_config.get('greeting', '')
            if greeting:
                logger.info(f"• 欢迎消息: \"{greeting}\"")
            else:
                logger.warning("• 欢迎消息: 未设置")
        else:
            logger.info("自动通过好友请求: 已禁用")
        
        # 牌堆配置
        logger.info("\n=== 牌堆配置 ===")
        decks_config = config.get('decks', {})
        deck_path = config.get('files', {}).get('deck_path', 'decks')
        
        if decks_config:
            logger.info(f"牌堆目录: {deck_path}")
            logger.info("已配置牌堆:")
            for deck_name, deck_file in decks_config.items():
                deck_file_path = os.path.join(current_dir, deck_path, deck_file)
                if os.path.exists(deck_file_path):
                    logger.info(f"• {deck_name}: {deck_file} (已加载)")
                else:
                    logger.warning(f"• {deck_name}: {deck_file} (文件不存在)")
        else:
            logger.warning("未配置任何牌堆")
        
        logger.info("\n=== 配置加载完成 ===")
        
        return config
        
    except Exception as e:
        logger.error(f"加载配置文件时发生错误: {e}", exc_info=True)
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
    
    # 初始化日志管理器
    log_manager = LogManager(config.get('logging', {}))
    
    wcf = Wcf()
    logger.info("正在启动骰子机器人...")
    
    handler = None  # 声明handler变量以便在finally中使用
    
    try:
        # 加载DND数据
        dnd_data_file = config.get('files', {}).get('dnd_data', 'DND5E23_4_2.json')
        dnd_data = load_dnd_data(dnd_data_file)
        
        if not dnd_data:
            logger.error(f"D&D数据加载失败或为空")
        
        # 加载DND 2024数据
        dnd2024_data_file = config.get('files', {}).get('dnd2024_data', 'dnd2024.json')
        dnd2024_data = load_dnd_data(dnd2024_data_file)
        
        if not dnd2024_data:
            logger.error(f"D&D 2024数据加载失败或为空")
        
        # 加载今日人品(jrrp)缓存
        from functions import load_jrrp_cache
        load_jrrp_cache()
        logger.info("已加载jrrp缓存")
        
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
        
        handler = CommandHandler(config)  # 传递配置参数
        # 初始化AI功能（包括天气服务）
        handler.init_ai(config)
        if not handler.qwen:
            logger.error("AI功能初始化失败")
            return
        
        # 创建事件循环
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 初始化天气调度器
        if handler.qwen.weather_service:
            # 设置天气服务的wcf实例
            handler.qwen.weather_service.wcf = wcf
            # 启动每日播报和预警监控
            loop.create_task(handler.qwen.weather_service.start_weather_report(handler.qwen.weather_service.check_and_broadcast))
        
        # 主循环
        while True:
            try:
                # 检查天气播报
                if handler and handler.qwen and handler.qwen.weather_service:
                    loop.run_until_complete(
                        handler.qwen.weather_service.check_and_broadcast(
                            list(handler.qwen.enabled_rooms)
                        )
                    )
                
                # 获取消息
                msg = wcf.get_msg()
                if msg:
                    handle_message(wcf, msg, config, dnd_data, dnd2024_data)
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
        # 在程序退出前保存所有因命令更改的开关到配置文件
        if handler and handler.qwen:
            try:
                import yaml
                # 获取配置文件的完整路径
                current_dir = os.path.dirname(os.path.abspath(__file__))
                config_path = os.path.join(current_dir, "config.yaml")
                
                # 读取当前配置
                with open(config_path, 'r', encoding='utf-8') as f:
                    # 使用RoundTripLoader保留注释和格式
                    from ruamel.yaml import YAML
                    yaml = YAML()
                    yaml.preserve_quotes = True
                    config = yaml.load(f)
                
                # 更新enabled_rooms和私聊功能状态
                if 'ai' in config and 'qwen' in config['ai']:
                    config['ai']['qwen']['group_chat']['enabled_rooms'] = list(handler.qwen.enabled_rooms)
                    config['ai']['qwen']['private_chat']['enabled'] = handler.qwen.private_chat_enabled
                    
                    # 写回配置文件
                    with open(config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config, f)
                    
                    logger.info(f"程序退出前已保存AI功能状态:")
                    logger.info(f"- 私聊功能: {'已启用' if handler.qwen.private_chat_enabled else '已禁用'}")
                    logger.info(f"- 已启用群聊: {list(handler.qwen.enabled_rooms)}")
            except Exception as e:
                logger.error(f"保存群聊AI功能状态失败 ({config_path}): {e}", exc_info=True)
        
        wcf.cleanup()
        logger.info("骰子机器人已停止")

if __name__ == "__main__":
    main() 