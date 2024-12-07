import logging
from typing import Callable, Dict, Optional
from wcferry import Wcf, WxMsg
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

class CommandHandler:
    """命令处理器类"""
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """只在第一次创建实例时初始化"""
        if not hasattr(self, 'initialized'):
            self.commands: Dict[str, Dict[str, any]] = {}
            self._register_commands()
            self.initialized = True
    
    def _register_commands(self):
        """注册所有命令处理函数及其所需参数"""
        self.commands = {
            '.drawhelp': {
                'handler': handle_drawhelp_command,
                'needs_config': True,
                'needs_dnd_data': False
            },
            '.r': {
                'handler': self.handle_roll_command,
                'needs_config': False,
                'needs_dnd_data': False
            },
            '.help': {
                'handler': self.handle_help_command,
                'needs_config': False,
                'needs_dnd_data': False
            },
            '.sys': {
                'handler': handle_sys_command,
                'needs_config': False,
                'needs_dnd_data': False
            },
            '.jrrp': {
                'handler': handle_jrrp_command,
                'needs_config': False,
                'needs_dnd_data': False
            },
            '.dnd': {
                'handler': handle_dnd_command,
                'needs_config': False,
                'needs_dnd_data': True
            },
            '.dicehelp': {
                'handler': handle_dicehelp_command,
                'needs_config': False,
                'needs_dnd_data': False
            },
            '.draw': {
                'handler': handle_draw_command,
                'needs_config': True,
                'needs_dnd_data': False
            }
        }
    
    def get_command_info(self, command: str) -> Optional[Dict[str, any]]:
        """获取命令对应的处理函数和参数需求"""
        for cmd_prefix, info in self.commands.items():
            if command.startswith(cmd_prefix):
                return info
        return None
    
    def handle_roll_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理骰子命令"""
        try:
            command = msg.content.split('.r', 1)[1].strip()
            roll_results, result = process_roll_command(command)
            nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
            reply = format_reply_message(nickname, roll_results, result)
            self._send_message(wcf, msg, reply)
            
        except Exception as e:
            logger.error(f"处理骰子命令出错: {e}", exc_info=True)
            self._send_message(wcf, msg, "处理命令时出错，请使用 .help 查看帮助")
    
    def handle_help_command(self, wcf: Wcf, msg: WxMsg, **kwargs) -> None:
        """处理帮助命令"""
        help_text = """可用指令说明：
.r [骰子表达式] - 投掷骰子（使用 .dicehelp 查看详细用法）
.dicehelp - 显示详细的骰子指令说明
.jrrp - 查看今日人品值（每人每天仅能查询一次）
.dnd [关键词] - 查询D&D规则内容
.draw [牌堆名] [数量] - 从指定牌堆抽取卡牌
.drawhelp - 显示所有牌堆信息和使用示例
.sys - 查看机器人运行状态

示例：
.r d20 - 投掷一个20面骰
.dnd 武器 - 查询与武器相关的规则
.jrrp - 查看今天的人品值
.draw dmt 1 - 从万象无常牌堆抽1张卡
.drawhelp - 查看所有牌堆信息"""
        
        self._send_message(wcf, msg, help_text)
    
    def execute_command(self, wcf: Wcf, msg: WxMsg, config: dict = None, dnd_data: dict = None) -> None:
        """执行命令"""
        try:
            command_info = self.get_command_info(msg.content)
            if not command_info:
                return
            
            kwargs = {}
            if command_info['needs_config']:
                kwargs['config'] = config
            if command_info['needs_dnd_data']:
                kwargs['dnd_data'] = dnd_data
            
            command_info['handler'](wcf, msg, **kwargs)
            
        except Exception as e:
            logger.error(f"执行命令出错: {e}", exc_info=True)
            self._send_message(wcf, msg, "命令执行出错，请稍后重试")
    
    def _send_message(self, wcf: Wcf, msg: WxMsg, content: str) -> None:
        """统一的消息发送函数"""
        if msg.roomid:
            wcf.send_text(content, msg.roomid)
        else:
            wcf.send_text(content, msg.sender)

def handle_message(wcf: Wcf, msg: WxMsg, config: dict, dnd_data: dict) -> None:
    """处理接收到的消息"""
    # 获取消息显示配置
    msg_config = config.get('message_display', {})
    msg_type_desc = MSG_TYPES.get(msg.type, f"未知消息类型({msg.type})")
    
    # 检查是否应该显示该类型的消息
    should_log = msg_config.get(f'type_{msg.type}', False)
    
    # 记录消息日志
    if should_log:
        log_content = msg.content if msg.type == 1 else f"[{msg_type_desc}]"
        sender_name = get_user_display_name(wcf, msg.sender, msg.roomid)
        chat_type = "群聊" if msg.roomid else "私聊"
        logger.debug(f"[{chat_type}] [{msg_type_desc}] {sender_name}: {log_content}")

    # 处理命令消息
    if msg.type == 1 and msg.content.startswith('.'):
        handler = CommandHandler()
        handler.execute_command(wcf, msg, config, dnd_data)