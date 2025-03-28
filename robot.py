import asyncio
import logging
import os
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
from character import character_manager
import xml.etree.ElementTree as ET
import shutil  # 添加到文件顶部的导入部分
import json
import time

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
            self.waiting_for_character_file = {}  # Dict[str, Optional[str]]  # user_id -> room_id
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
            ),
            '.char': CommandInfo(
                handler=self.handle_character_command,
                needs_config=False,
                needs_dnd_data=False,
                description='角色卡管理'
            ),
            '.c': CommandInfo(
                handler=self.handle_check_command,
                needs_config=False,
                needs_dnd_data=False,
                description='进行技能检定'
            ),
            '.grow': CommandInfo(
                handler=self.handle_grow_command,
                needs_config=False,
                needs_dnd_data=False,
                description='进行技能成长\n用法: .grow <技能名>'
            ),
            '.setgrow': CommandInfo(
                handler=self.handle_setgrow_command,
                needs_config=False,
                needs_dnd_data=False,
                description='[管理员] 设置角色成长次数\n用法: .setgrow <次数>'
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

骰子指令:
• .r [表达式]   - 投掷骰子 (.dicehelp 查看详细用法)
  示例: .r d20a (投掷d20优势骰)
       .r 2d6+5 (投掷2个6面骰加5)

牌堆与人品:
• .draw [牌堆] [数量] - 从指定牌堆抽卡
• .jrrp        - 今日人品（从64卦中抽取一卦）

角色卡系统:
• .char        - 角色卡管理 (.char help 查看详细用法)
• .c [技能名]   - 进行技能检定
• .grow [技能名] [次数] - 进行技能成长

查询服务:
• .dnd [关键词] - 查询D&D规则内容
• .weather [城市] [天数] - 查看天气信息
  示例: .weather 北京 3d (查看北京未来3天天气)

AI功能:
• 群聊中@机器人 - 使用AI聊天功能
• 私聊直接发送消息 - 开始AI对话

管理员指令:
• .ai room on/off - 开启/关闭当前群聊的AI功能
• .setgrow [角色名] [点数] - 设置角色成长点数
• .sys - 查看机器人运行状态

详细说明:
• .dicehelp  - 显示骰子指令详细说明
• .drawhelp  - 显示抽卡指令详细说明
• .char help - 显示角色卡指令详细说明"""

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
            
            # 检查是否异步处理函数
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
            logger.error(f"发送消息失败: {e}")
    
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

    async def handle_character_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理角色卡相关命令"""
        try:
            parts = msg.content.split('.char', 1)[1].strip().split()
            if not parts:
                self._send_message(wcf, msg, "请使用 .char help 查看角色卡命令帮助")
                return
                
            subcmd = parts[0].lower()
            
            if subcmd == "list":
                # 显示所有角色卡列表
                info = character_manager.list_characters()
                self._send_message(wcf, msg, info)
                return
                
            elif subcmd == "use":
                if len(parts) < 2:
                    self._send_message(wcf, msg, "请指定角色名称，如: .char use 川尻早人")
                    return
                char_name = ' '.join(parts[1:])
                success, message = character_manager.use_character(msg.sender, msg.roomid, char_name)
                self._send_message(wcf, msg, message)
                return
                
            elif subcmd == "release":
                success, message = character_manager.release_character(msg.sender, msg.roomid)
                self._send_message(wcf, msg, message)
                return
                
            elif subcmd == "info":
                if len(parts) < 2:
                    char_name = character_manager.get_current_character(msg.sender, msg.roomid)
                    if not char_name:
                        self._send_message(wcf, msg, "请指定角色名称，或使用 .char use 设置当前角色")
                        return
                else:
                    char_name = ' '.join(parts[1:])
                
                info = character_manager.show_character_info(char_name)
                self._send_message(wcf, msg, info)
                return
                
            elif subcmd == "load":
                # 等待用户上传角色卡文件
                self.waiting_for_character_file[msg.sender] = msg.roomid
                help_text = "请上传JSON格式的角色卡文件（最大1MB）"
                self._send_message(wcf, msg, help_text)
                return
                
            elif subcmd == "status":
                # 显示所有角色卡的使用状态
                info = character_manager.show_character_status()
                self._send_message(wcf, msg, info)
                return
                
            elif subcmd == "force-release" or (subcmd == "force" and len(parts) > 1 and parts[1].lower() == "release"):
                # 检查是否是管理员
                if not self.qwen.is_admin(msg.sender):
                    self._send_message(wcf, msg, "只有管理员可以使用此命令")
                    return
                
                # 处理两种不同的命令格式: `.char force-release 角色名` 或 `.char force release 角色名`
                if subcmd == "force-release":
                    if len(parts) < 2:
                        self._send_message(wcf, msg, "请指定要释放的角色名称")
                        return
                    char_name = ' '.join(parts[1:])
                else:  # force release
                    if len(parts) < 3:
                        self._send_message(wcf, msg, "请指定要释放的角色名称")
                        return
                    char_name = ' '.join(parts[2:])
                
                success, message = await character_manager.force_release_character(char_name)
                
                # 记录强制释放操作的历史记录
                if success:
                    character_manager.record_operation(char_name, msg.sender, "force_release")
                
                self._send_message(wcf, msg, message)
                return
                
            elif subcmd == "history":
                # 处理角色卡操作历史查询
                try:
                    # 处理可能的限制参数
                    limit = 20  # 默认显示20条记录
                    
                    # 检查参数中是否包含数字作为limit
                    char_name_parts = []
                    for part in parts[1:]:
                        if part.isdigit():
                            limit = int(part)
                        else:
                            char_name_parts.append(part)
                    
                    # 确定角色名
                    if not char_name_parts:
                        char_name = character_manager.get_current_character(msg.sender, msg.roomid)
                        if not char_name:
                            self._send_message(wcf, msg, "请指定角色名称，或使用 .char use 设置当前角色")
                            return
                    else:
                        char_name = ' '.join(char_name_parts)
                    
                    # 获取并显示操作历史记录
                    history = character_manager.show_character_history(char_name)
                    self._send_message(wcf, msg, history)
                    return
                except ValueError:
                    self._send_message(wcf, msg, "参数格式错误，请使用：.char history [角色名]")
                    return
                
            elif subcmd == "help":
                help_text = """🎭 角色卡管理命令：
📥 .char load - 上传角色卡文件
📋 .char list - 显示所有可用角色卡
📊 .char info [角色名] - 显示角色卡基本信息
👤 .char use <角色名> - 设置当前使用的角色
🔄 .char release - 释放当前使用的角色
👥 .char status - 显示所有角色卡的使用状态
📖 .char history [角色名] - 显示角色卡操作历史
⚠️ .char force release <角色名> - [管理员] 强制释放角色卡
📜 .char help - 显示本帮助信息

⚠️ 注意事项：
1. 一个角色卡同时只能被一个用户使用
2. 使用角色卡后，可以省略角色名称
3. 使用 .char release 释放当前使用的角色
4. 角色卡文件大小不能超过1MB"""
                self._send_message(wcf, msg, help_text)
                return
                
            else:
                self._send_message(wcf, msg, f"未知的角色卡命令: {subcmd}\n使用 .char help 查看帮助")
                
        except Exception as e:
            logger.error(f"处理角色卡命令出错: {e}")
            self._send_message(wcf, msg, "处理命令时出错，请重试")

    def handle_check_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理技能检定命令"""
        try:
            # 获取技能名称
            skill_name = msg.content.split('.c', 1)[1].strip()
            if not skill_name:
                self._send_message(wcf, msg, "请指定要检定的技能，如：.c 侦查")
                return
            
            # 调用 check_skill 方法时传递所有必需参数
            success, message = character_manager.check_skill(
                user_id=msg.sender,
                room_id=msg.roomid,
                skill_name=skill_name
            )
            
            self._send_message(wcf, msg, message)
            
        except Exception as e:
            logger.error(f"处理检定命令出错: {e}")
            self._send_message(wcf, msg, "处理命令时出错，请重试")

    async def handle_grow_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理技能成长命令"""
        try:
            parts = msg.content.split('.grow', 1)[1].strip().split()
            if not parts:
                self._send_message(wcf, msg, "请指定要成长的技能，如：.grow 侦查")
                return
            
            if parts[0].lower() == "history":
                # 处理成长历史查询
                try:
                    # 处理可能的限制参数
                    limit = 20  # 默认显示20条记录
                    
                    # 检查参数中是否包含数字作为limit
                    char_name_parts = []
                    for part in parts[1:]:
                        if part.isdigit():
                            limit = int(part)
                        else:
                            char_name_parts.append(part)
                    
                    # 确定角色名
                    if not char_name_parts:
                        char_name = character_manager.get_current_character(msg.sender, msg.roomid)
                        if not char_name:
                            self._send_message(wcf, msg, "请指定角色名称，或使用 .char use 设置当前角色")
                            return
                    else:
                        char_name = ' '.join(char_name_parts)
                    
                    # 获取并显示历史记录
                    history = character_manager.show_growth_history(char_name, limit=limit)
                    self._send_message(wcf, msg, history)
                    return
                except ValueError:
                    self._send_message(wcf, msg, "参数格式错误，请使用：.grow history [角色名] [显示条数]")
                    return
            
            skill_name = ' '.join(parts)
            success, message = character_manager.grow_skill(msg.sender, msg.roomid, skill_name)
            self._send_message(wcf, msg, message)
            
        except Exception as e:
            logger.error(f"处理技能成长命令出错: {e}")
            self._send_message(wcf, msg, "处理命令时出错，请重试")

    async def handle_setgrow_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理设置成长次数命令"""
        try:
            # 检查是否是管理员
            if not self.qwen or not self.qwen.is_admin(msg.sender):
                self._send_message(wcf, msg, "只有管理员可以使用此命令")
                return
            
            parts = msg.content.split('.setgrow', 1)[1].strip().split()
            if len(parts) < 2:
                self._send_message(wcf, msg, "请指定角色名和成长次数，如：.setgrow 川尻早人 5")
                return
            
            try:
                points = int(parts[-1])
                char_name = ' '.join(parts[:-1])
            except ValueError:
                self._send_message(wcf, msg, "成长次数必须是数字")
                return
            
            # 获取当前成长点数
            current_points = character_manager.db.get_growth_points(char_name)
            
            # 调用数据库设置成长点数
            success, message = character_manager.db.set_growth_points(char_name, points)
            
            # 记录成长历史
            if success:
                logger.debug(f"记录成长点数变更: {char_name}, {current_points} -> {points}, 用户: {msg.sender}")
                character_manager.record_growth_points_change(
                    char_name=char_name,
                    user_id=msg.sender,
                    old_value=str(current_points),
                    new_value=str(points)
                )
                logger.debug(f"成长点数变更记录完成")
                
                # 生成更友好的消息，明确表示增减
                if points > current_points:
                    message = f"已增加角色「{char_name}」的成长次数：{current_points} → {points} (+{points-current_points})"
                elif points < current_points:
                    message = f"已减少角色「{char_name}」的成长次数：{current_points} → {points} ({points-current_points})"
                # 如果相等，使用原始消息
                
            self._send_message(wcf, msg, message)
            
        except Exception as e:
            logger.error(f"处理设置成长次数命令出错: {e}")
            self._send_message(wcf, msg, "处理命令时出错，请重试")

class DiceRobot:
    async def handle_message(self, wcf: Wcf, msg: WxMsg):
        """主消息处理函数"""
        try:
            # 1. 快速的数据库检查可以保持同步
            if not self.db.is_group_enabled(msg.roomid):
                return
                
            # 2. 耗时的命令处理使用异步
            if msg.content.startswith('.char'):
                await self.handle_character_command(wcf, msg)
            elif msg.content.startswith('.grow'):
                await self.handle_growth_command(wcf, msg)
            elif msg.content.startswith('.ai'):
                await self.handle_ai_chat(wcf, msg)
                
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            
    async def handle_character_command(self, wcf: Wcf, msg: WxMsg):
        """处理角色卡命令"""
        try:
            parts = msg.content.split()
            
            # 3. 简单的数据库操作可以保持同步
            if parts[1] == 'list':
                chars = self.db.get_character_list(msg.sender)
                await self.send_message(wcf, msg, format_char_list(chars))
                
            # 4. 复杂或耗时的操作使用异步
            elif parts[1] == 'use':
                char_name = ' '.join(parts[2:])
                result = await self.character_manager.use_character(
                    msg.sender,
                    msg.roomid,
                    char_name
                )
                await self.send_message(wcf, msg, result)
                
        except Exception as e:
            logger.error(f"处理角色卡命令失败: {e}")

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
                
        # 处理文件消息，用于加载角色卡
        elif msg.type == 49:  # 文件消息类型
            try:
                # 检查是否是通过 .char load 命令触发的文件上传
                handler = CommandHandler(config)
                if msg.sender not in handler.waiting_for_character_file:
                    return
                    
                # 获取对应的群聊ID
                room_id = handler.waiting_for_character_file[msg.sender]
                if room_id != msg.roomid:
                    return
                    
                try:
                    # 解析文件信息
                    root = ET.fromstring(msg.content)
                    appmsg = root.find('appmsg')
                    if appmsg is None or appmsg.find('title') is None:
                        return
                        
                    title = appmsg.find('title').text
                    if not title.lower().endswith('.json'):
                        wcf.send_text("请上传JSON格式的角色卡文件", msg.roomid or msg.sender)
                        return
                        
                    # 读取源文件内容
                    source_path = msg.extra.replace('/', '\\')
                    logger.debug(f"等待文件: {source_path}")
                    
                    # 等待并读取文件
                    if not wait_for_file(source_path):
                        wcf.send_text("等待文件超时，请重试", msg.roomid or msg.sender)
                        return
                    
                    try:
                        with open(source_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                            
                        # 预验证JSON格式
                        try:
                            json.loads(file_content)
                        except json.JSONDecodeError:
                            wcf.send_text("文件格式错误，请确保是有效的JSON文件", msg.roomid or msg.sender)
                            return
                            
                        # 处理角色卡数据
                        loop = asyncio.get_event_loop()
                        success, message = loop.run_until_complete(
                            character_manager.load_character(
                                file_content,
                                msg.sender,
                                msg.roomid
                            )
                        )
                        wcf.send_text(message, msg.roomid or msg.sender)
                        
                    except UnicodeDecodeError:
                        wcf.send_text("文件编码错误，请确保使用UTF-8编码", msg.roomid or msg.sender)
                    except Exception as e:
                        logger.error(f"读取文件失败: {e}")
                        wcf.send_text("读取文件失败，请重试", msg.roomid or msg.sender)
                        
                except ET.ParseError as e:
                    logger.error(f"解析文件信息失败: {e}")
                    wcf.send_text("无法解析文件信息，请重试", msg.roomid or msg.sender)
                    
            except Exception as e:
                logger.error(f"处理角色卡文件失败: {e}", exc_info=True)
                wcf.send_text("处理文件失败，请重试", msg.roomid or msg.sender)
            
            finally:
                # 无论成功与否，都清除等待状态
                handler = CommandHandler(config)
                if msg.sender in handler.waiting_for_character_file:
                    del handler.waiting_for_character_file[msg.sender]
                
            return
                
    except Exception as e:
        logger.error(f"处理消息时出错: {e}", exc_info=True)

def ensure_character_dir() -> str:
    """确保角色卡数据目录存在，返回目录路径"""
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    char_dir = os.path.join(current_dir, 'data', 'characters')
    os.makedirs(char_dir, exist_ok=True)
    return char_dir

def wait_for_file(file_path: str, max_retries: int = 20, delay: float = 0.5) -> bool:
    """等待文件下载完成"""
    import time
    import os
    
    for i in range(max_retries):
        if os.path.exists(file_path):
            try:
                # 尝试打开文件，确保文件已完全写入
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.read(1)  # 尝试读取一个字符
                time.sleep(0.5)  # 额外等待以确保文件完全写入
                return True
            except:
                pass  # 如果文件无法打开，继续等待
        logger.debug(f"等待文件下载，尝试 {i+1}/{max_retries}")
        time.sleep(delay)
    return False
        