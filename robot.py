import asyncio
import logging
from typing import Callable, Dict, Optional, List, Any, Union
from dataclasses import dataclass
from wcferry import Wcf, WxMsg
from weather import WeatherService
from functions import (
    handle_dicehelp_command,
    handle_jrrp_command,
    handle_dnd_command,
    handle_draw_command,
    handle_drawhelp_command,
    handle_sys_command,
    get_user_display_name
)
from dice_roller import process_roll_command, format_reply_message
from ai_chat import QwenChat, handle_ai_chat
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

# 消息类型映射
MSG_TYPES = {
    1: "文本消息",
    3: "图片消息",
    34: "语音消息",
    43: "视频消息",
    42: "名片消息",
    48: "位置消息",
    47: "表情消息",
    49: "文件消息",
    10000: "系统消息",
    37: "好友确认消息",
    40: "POSSIBLEFRIEND_MSG",
    41: "微信名片消息",
    44: "视频通话消息",
    50: "语音通话消息",
    51: "状态通知消息",
    62: "小视频消息",
}

@dataclass
class CommandInfo:
    """命令信息数据类"""
    handler: Callable
    needs_config: bool
    needs_dnd_data: bool
    description: str = ""

class CommandHandler:
    """命令处理器类"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: dict):
        """只在第一次创建实例时初始化"""
        if not hasattr(self, 'initialized'):
            self.commands: Dict[str, CommandInfo] = {}
            self.qwen = None
            self._register_commands()
            self.initialized = True
    
    def init_ai(self, config: dict):
        """初始化 AI 聊天"""
        try:
            ai_config = config.get('ai', {}).get('qwen', {})
            api_key = ai_config.get('api_key')
            model = ai_config.get('model', 'qwen-turbo')
            control_config = ai_config.get('control', {})
            app_id = ai_config.get('app_id')
            
            # 初始化 QwenChat 实例
            self.qwen = QwenChat(
                api_key=api_key,
                model=model,
                admin_wxid=control_config.get('admin_wxid', 'jumper_rong'),
                group_config=ai_config.get('group_chat', {}),
                app_id=app_id
            )
            
            # 如果配置了天气服务，则初始化
            weather_config = ai_config.get('weather')
            if weather_config:
                weather_service = WeatherService(weather_config)
                self.qwen.set_weather_service(weather_service)
            
        except Exception as e:
            logger.error(f"初始化 AI 功能出错: {e}")
            self.qwen = QwenChat(
                admin_wxid='jumper_rong',
                group_config={}
            )
    
    def _register_commands(self) -> None:
        """注册所有命令处理函数及其所需参数"""
        self.commands: Dict[str, CommandInfo] = {
            '.weather': CommandInfo(
                handler=self.handle_weather_command,
                needs_config=True,
                needs_dnd_data=False,
                description='查看天气信息\n用法: .weather [城市名] [3d/7d]'
            ),
            '.adminhelp': CommandInfo(
                handler=self.handle_adminhelp_command,
                needs_config=False,
                needs_dnd_data=False
            ),
            '.drawhelp': CommandInfo(
                handler=handle_drawhelp_command,
                needs_config=True,
                needs_dnd_data=False
            ),
            '.r': CommandInfo(
                handler=self.handle_roll_command,
                needs_config=False,
                needs_dnd_data=False,
                description='投掷骰子（使用 .dicehelp 查看详细用法）'
            ),
            '.help': CommandInfo(
                handler=self.handle_help_command,
                needs_config=False,
                needs_dnd_data=False,
                description='显示帮助信息'
            ),
            '.sys': CommandInfo(
                handler=handle_sys_command,
                needs_config=False,
                needs_dnd_data=False,
                description='查看机器人运行状态'
            ),
            '.jrrp': CommandInfo(
                handler=handle_jrrp_command,
                needs_config=False,
                needs_dnd_data=False,
                description='查看今日人品值'
            ),
            '.dnd': CommandInfo(
                handler=handle_dnd_command,
                needs_config=False,
                needs_dnd_data=True,
                description='查询D&D规则内容'
            ),
            '.dicehelp': CommandInfo(
                handler=handle_dicehelp_command,
                needs_config=False,
                needs_dnd_data=False,
                description='显示详细的骰子指令说明'
            ),
            '.draw': CommandInfo(
                handler=handle_draw_command,
                needs_config=True,
                needs_dnd_data=False,
                description='从指定牌堆抽卡牌'
            ),
            '.ai': CommandInfo(
                handler=self.handle_ai_command,
                needs_config=True,
                needs_dnd_data=False,
                description='AI功能控制（仅管理员可用）'
            )
        }
    
    def get_command_info(self, command: str) -> Optional[CommandInfo]:
        """获取命令对应的处理函数参数需求"""
        # 处理所有 .ai 开头的命令
        if command.startswith('.ai'):
            return self.commands.get('.ai')
        
        # 处理其他命令
        for cmd_prefix, info in self.commands.items():
            if command.startswith(cmd_prefix):
                return info
        return None
    
    def handle_roll_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理骰子命令"""
        try:
            command = msg.content.split('.r', 1)[1].strip()
            roll_results, result, extra_text = process_roll_command(command)
            nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
            reply = format_reply_message(nickname, result, extra_text)
            self._send_message(wcf, msg, reply)
            
        except Exception as e:
            logger.error(f"处理骰子命令出错: {e}", exc_info=True)
            self._send_message(wcf, msg, "处理命令时出错，请使用 .help 查看帮助")
    
    def handle_help_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理帮助命令"""
        help_text = """🤖 骰子机器人指令说明:

基础指令:
• .r [表达式]   - 投掷骰子 (.dicehelp 查看详细用法)
• .jrrp        - 查看今日人品
• .dnd [关键词] - 查询D&D规则内容
• .draw [牌堆]  - 从指定牌堆抽卡
• .weather     - 查看天气信息

管理员指令:
• .ai room on/off    - 开启/关闭当前群聊的AI功能
• .sys               - 查看机器人运行状态

详细说明:
• .dicehelp  - 显示骰子指令详细说明
• .drawhelp  - 显示抽卡指令详细说明
• .adminhelp - 显示管理员指令详细说明"""

        self._send_message(wcf, msg, help_text)
    
    def execute_command(self, wcf: Wcf, msg: WxMsg, config: dict = None, dnd_data: dict = None) -> None:
        """执行命令"""
        try:
            command_info = self.get_command_info(msg.content)
            if not command_info:
                command = msg.content.split()[0]
                help_text = f"未知命令: {command}\n请使用 .help 查看可用命令列表"
                self._send_message(wcf, msg, help_text)
                return
            
            kwargs = {}
            if command_info.needs_config:
                kwargs['config'] = config
            if command_info.needs_dnd_data:
                kwargs['dnd_data'] = dnd_data
            
            handler = command_info.handler
            
            # 检查是否异步处理数
            if asyncio.iscoroutinefunction(handler):
                loop = asyncio.get_event_loop()
                loop.run_until_complete(handler(wcf, msg, **kwargs))
            else:
                handler(wcf, msg, **kwargs)
            
        except Exception as e:
            logger.error(f"执行命令出错: {e}", exc_info=True)
            self._send_message(wcf, msg, "命令执行出错，请稍后重试")
    
    def _send_message(self, wcf: Wcf, msg: WxMsg, content: str) -> None:
        """统一的消息发送函数"""
        try:
            if msg.roomid:
                wcf.send_text(content, msg.roomid)
            else:
                wcf.send_text(content, msg.sender)
        except Exception as e:
            logger.error(f"发送消息失败: {e}", exc_info=True)
    
    async def handle_ai_command(self, wcf: Wcf, msg: WxMsg, config: dict = None, **kwargs) -> None:
        """处理 AI 聊天命令"""
        if not self.qwen:
            self.init_ai(config)
        
        # 检查是否是管理员
        if not self.qwen.is_admin(msg.sender):
            reply = "只有管理员可以使用.ai命令"
            self._send_message(wcf, msg, reply)
            return
        
        # 检查命令格式
        content = msg.content.strip()
        
        if content == '.ai test':
            # 处理 .ai test 命令
            try:
                # 获取配置状态
                config_status = self.qwen.test_ai_function()
                
                # 如果配置正常，进行对话测试
                if self.qwen.is_available():
                    test_prompt = "请用一句话介绍你自己"
                    ai_response = await self.qwen.get_response(msg.sender, test_prompt)
                    if ai_response:
                        test_result = (
                            f"{config_status}\n\n"
                            f"对话测试:\n"
                            f"问: {test_prompt}\n"
                            f"答: {ai_response}"
                        )
                    else:
                        test_result = (
                            f"{config_status}\n\n"
                            f"对话测试: 失败 - 未获得响应"
                        )
                else:
                    test_result = config_status
                
                # 发送测试结果
                self._send_message(wcf, msg, test_result)
                
            except Exception as e:
                logger.error(f"AI测试出错: {e}", exc_info=True)
                self._send_message(wcf, msg, "AI测试执行出错，请查看日志")
            return
        
        # 处理群聊AI功能开关
        if content.startswith('.ai room'):
            if content == '.ai room on' or content == '.ai room off':
                enable = content.endswith('on')
                if msg.roomid:
                    if enable:
                        self.qwen.enabled_rooms.add(msg.roomid)
                        reply = "已在本群启用AI功能"
                    else:
                        self.qwen.enabled_rooms.discard(msg.roomid)
                        reply = "已在本群禁用AI功能"
                else:
                    reply = "此命令只能在群聊中使用"
                
                self._send_message(wcf, msg, reply)
                return
        
        # 如果命令格式不正确，显示帮助信息
        help_text = """AI 命令用法:
.ai test - 测试 AI 功能
.ai sidetext on/off - 开启/关闭私聊功能
.ai room on/off - 开启/关闭群聊功能"""
        self._send_message(wcf, msg, help_text)
    
    def handle_adminhelp_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理管理员帮助命令"""
        if not self.qwen or not self.qwen.is_admin(msg.sender):
            self._send_message(wcf, msg, "只有管理员可以使用此命令")
            return

        admin_help = """👑 管理员指令说明:

AI功能控制:
• .ai room on/off
  - 开启/关闭当前群聊的AI功能
  - 示例: .ai room on

系统命令:
• .sys
  - 查看机器人运行状态
  - 显示AI功能配置、群聊状态等

注意事项:
1. 群聊中需要@机器人才会响应
2. 私聊可以直接对话
3. 配置更改会自动保存到配置文件"""

        self._send_message(wcf, msg, admin_help)
    
    async def handle_weather_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理天气查询命令"""
        if not self._check_weather_service():
            return
        
        try:
            city, days = self._parse_weather_command(msg.content)
            weather_info = await self._get_weather_info(city, days)
            
            if weather_info:
                self._send_message(wcf, msg, weather_info)
            
        except Exception as e:
            self._handle_weather_error(wcf, msg, e)
    
    def _check_weather_service(self) -> bool:
        """检查天气服务是否可用"""
        if not self.qwen or not self.qwen.weather_service:
            logger.error("天气服务未初始化")
            return False
        return True
    
    def _parse_weather_command(self, content: str) -> tuple[str, str]:
        """解析天气命令参数"""
        parts = content.split('.weather', 1)[1].strip().split()
        
        # 默认值
        city = self.qwen.weather_service.default_city
        days = 'now'
        
        if parts:
            # 检查最后一个参数是否是天数后缀
            if parts[-1].lower() in ['3d', '7d']:
                days = parts[-1][0]  # 提取数字
                parts = parts[:-1]  # 移除天数参数
            
            # 剩余部分作为城市名
            if parts:
                city = ' '.join(parts)
        
        return city, days
    
    async def _get_weather_info(self, city: str, days: str) -> Optional[str]:
        """获取天气信息"""
        try:
            weather_info = await self.qwen.weather_service.get_weather(days, city)
            if not weather_info:
                return f"获取{city}的天气信息失败"
            
            if days == 'now':
                return await self._get_current_weather_info(city, weather_info)
            else:
                return self._get_forecast_weather_info(city, days, weather_info)
                
        except Exception as e:
            logger.error(f"获取天气信息失败: {e}", exc_info=True)
            return None
    
    async def _get_current_weather_info(self, city: str, weather_info: str) -> str:
        """获取当前天气信息"""
        indices_info = await self.qwen.weather_service.get_indices(city)
        warning_info = await self.qwen.weather_service.get_warning(city)
        
        # 组合信息
        info_parts = [
            f"{city}天气信息:",
            "",
            weather_info
        ]
        
        if indices_info:
            info_parts.extend(["", indices_info])
        
        if warning_info:
            info_parts.extend(["", warning_info])
        else:
            info_parts.extend(["", "当前无预警信息"])
        
        return "\n".join(info_parts)
    
    def _get_forecast_weather_info(self, city: str, days: str, weather_info: str) -> str:
        """获取天气预报信息"""
        return f"{city}未来{days}天天预报:\n\n{weather_info}"
    
    def _handle_weather_error(self, wcf: Wcf, msg: WxMsg, error: Exception) -> None:
        """处理天气命令错误"""
        logger.error(f"处理天气命令失败: {error}", exc_info=True)
        error_msg = "获取天气信息失败,请稍后重试"
        self._send_message(wcf, msg, error_msg)

def handle_message(wcf: Wcf, msg: WxMsg, config: dict, dnd_data: dict) -> None:
    """处理收到的消息"""
    try:
        # 获取消息显示设置
        msg_config = config.get('message_display', {})
        msg_type_desc = MSG_TYPES.get(msg.type, f"未知消息类型({msg.type})")
        
        # 判断是否为私聊(wxid 和 room_id 相同)
        is_private = msg.roomid and msg.sender == msg.roomid
        if is_private:
            msg.roomid = None
            
        # 检查是否应该显示该类型的消息
        should_log = msg_config.get(f'type_{msg.type}', False)
        
        # 记录消息日志
        if should_log:
            log_content = msg.content if msg.type == 1 else f"[{msg_type_desc}]"
            sender_name = get_user_display_name(wcf, msg.sender, msg.roomid)
            chat_type = "私聊" if is_private else "群聊"
            logger.debug(f"[{chat_type}] [{msg_type_desc}] {sender_name}: {log_content}")

        # 处理命令消息
        if msg.type == 1:
            handler = CommandHandler(config)
            
            # 优先处理所有"."开头的命令
            if msg.content.startswith('.'):
                logger.debug(f"处理命令消息: {msg.content}")
                try:
                    handler.execute_command(wcf, msg, config, dnd_data)
                    logger.debug(f"命令处理完成: {msg.content}")
                except Exception as e:
                    logger.error(f"命令处理失败: {msg.content} - {e}", exc_info=True)
                return
            
            # 如果不是命令则处理AI对话
            if handler.qwen and handler.qwen.is_available():
                # 检查是否是群聊消息
                if msg.roomid:
                    # 检查是否@了机器人
                    if not msg.is_at:
                        return
                    
                    # 忽略@所有人的消息
                    if "@所有人" in msg.content:
                        return
                    
                    # 检查群聊是否在启用列表中
                    if not handler.qwen.is_group_chat_allowed(msg.roomid):
                        wcf.send_text("本群AI功能未启用，请联系管理员使用.ai room on开启", msg.roomid)
                        return
                
                # 创建事件循环并运行AI对话
                loop = asyncio.get_event_loop()
                loop.run_until_complete(handle_ai_chat(wcf, msg, handler.qwen))
                
    except Exception as e:
        logger.error(f"处理消息时出错: {e}", exc_info=True)
        