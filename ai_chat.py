import dashscope
from typing import Optional, List, Dict
from wcferry import Wcf, WxMsg
import logging
from datetime import datetime, timedelta
import asyncio
from functools import partial
import json
import requests
from weather import WeatherService
import os

logger = logging.getLogger(__name__)

# 添加会话管理
class ChatSession:
    def __init__(self):
        self.sessions = {}  # 存储用户会话状态
        
    def start_session(self, user_id: str) -> None:
        """开始新会话"""
        self.sessions[user_id] = {
            'active': True,
            'start_time': datetime.now(),
            'expire_time': datetime.now() + timedelta(hours=72)
        }
        
    def is_session_active(self, user_id: str) -> bool:
        """检查会话是否有效"""
        if user_id not in self.sessions:
            return False
            
        session = self.sessions[user_id]
        if datetime.now() > session['expire_time']:
            del self.sessions[user_id]
            return False
            
        return session['active']
    
    def end_session(self, user_id: str) -> None:
        """结束会话"""
        if user_id in self.sessions:
            del self.sessions[user_id]

class QwenChat:
    """通义千问聊天类"""
    
    def __init__(self, api_key: str = None, model: str = "qwen-turbo", 
                 admin_wxid: str | list = "jumper_rong", group_config: dict = None, app_id: str = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model = model
        self.group_config = group_config or {}
        self.weather_service = None
        self.sessions: Dict[str, dict] = {}
        self.session_timeout = 30  # 会话超时时间（分钟）
        self.admin_wxids = [admin_wxid] if isinstance(admin_wxid, str) else admin_wxid
        self.app_id = app_id
        
        # 初始化已启用的群聊
        enabled_rooms = self.group_config.get('enabled_rooms', [])
        self.enabled_rooms = set(enabled_rooms)
        
        # 添加私聊配置
        private_chat_config = self.group_config.get('private_chat', {})
        self.private_chat_enabled = private_chat_config.get('enabled', False)
        self.private_chat_whitelist = set(private_chat_config.get('whitelist', []))
        
        # 设置dashscope的API key和应用ID
        if self.api_key:
            dashscope.api_key = self.api_key
        if app_id:
            dashscope.app_id = app_id

        # 检查API Key和应用ID
        self._check_api_configuration()
    
    def _check_api_configuration(self):
        """检查API Key和应用ID的配置情况"""
        if not self.api_key:
            logger.error("DashScope API key未设置")
        if not self.app_id:
            logger.error("DashScope 应用ID未设置")
        if self.api_key and self.app_id:
            logger.info("DashScope API key和应用ID已正确配置")
    
    def set_weather_service(self, weather_service: WeatherService):
        """设置天气服务"""
        self.weather_service = weather_service
        # 同步已启用的群聊列表
        self.weather_service.enabled_rooms = self.enabled_rooms
        logger.info(f"已同步天气服务群聊列表: {len(self.enabled_rooms)}个群")
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return bool(self.api_key and self.app_id)
    
    def _check_session_active(self, session_id: str) -> bool:
        """内部方法：检查会话是否活跃"""
        if session_id not in self.sessions:
            return False
        
        last_active = self.sessions[session_id]['last_active']
        timeout = timedelta(minutes=self.session_timeout)
        return datetime.now() - last_active <= timeout
    
    def _create_new_session(self, session_id: str) -> dict:
        """内部方法：创建新会话"""
        self.sessions[session_id] = {
            'messages': [],
            'last_active': datetime.now()
        }
        return self.sessions[session_id]
    
    def get_session(self, session_id: str) -> dict:
        """获取或创建会话"""
        if not self._check_session_active(session_id):
            return self._create_new_session(session_id)
        self.sessions[session_id]['last_active'] = datetime.now()
        return self.sessions[session_id]
    
    def update_session(self, session_id: str, message: str, role: str = "user"):
        """更新会话消息"""
        session = self.get_session(session_id)
        session['messages'].append({
            'role': role,
            'content': message
        })
        session['last_active'] = datetime.now()
    
    def _prepare_messages(self, session_id: str) -> List[Dict[str, str]]:
        """准备消息历史"""
        session = self.get_session(session_id)
        return session.get('messages', [])
    
    async def _call_api(self, messages: List[Dict[str, str]], session_id: Optional[str] = None) -> Optional[str]:
        """调用通义千问API"""
        max_retries = 3
        retry_count = 0
        
        try:
            if not dashscope.api_key or not dashscope.app_id:
                logger.error("DashScope API key或应用ID未设置")
                return None
            
            logger.debug(f"使用的模型: {self.model}")
            logger.debug(f"使用的应用ID: {dashscope.app_id}")
            logger.debug(f"调用API的消息: {messages}")
            
            response = dashscope.Application.call(
                api_key=self.api_key,
                app_id=self.app_id,
                prompt=messages[-1]['content'],
                session_id=session_id
            )
            
            if response.status_code == 200:
                logger.debug(f"API响应: {response.output}")
                return response.output.text
            else:
                logger.error(f"HTTP返回码：{response.status_code}")
                logger.error(f"错误码：{response.code}")
                logger.error(f"错误信息：{response.message}")
                return "AI服务暂时不可用，请稍后再试"
                
        except Exception as e:
            logger.error(f"调用API时出错: {e}")
            return None
    
    def is_user_in_whitelist(self, user_wxid: str) -> bool:
        """检查用户是否在私聊白名单中"""
        whitelist = self.group_config.get('private_chat', {}).get('whitelist', [])
        return user_wxid in whitelist
    
    async def get_response(self, session_id: str, message: str) -> Optional[str]:
        """获取AI响应"""
        try:
            if not self.is_available():
                return "AI 服务未正确配置"
            
            # 更新用户消息
            self.update_session(session_id, message)
            
            # 准备消息历史
            messages = self._prepare_messages(session_id)
            
            # 调用API获取响应
            response = await self._call_api(messages, session_id)
            
            if response:
                # 更新AI响应到会话
                self.update_session(session_id, response, role="assistant")
                return response
            return "抱歉，我现在无法正确理解您的问题，请稍后再试"
            
        except Exception as e:
            logger.error(f"获取AI响应失败: {e}")
            return "抱歉,处理您的请求时出现错误"
    
    def clear_session(self, session_id: str):
        """清除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def clean_expired_sessions(self):
        """清理过期会话"""
        current_time = datetime.now()
        timeout = timedelta(minutes=self.session_timeout)
        expired_sessions = [
            session_id for session_id, session in self.sessions.items()
            if current_time - session['last_active'] > timeout
        ]
        for session_id in expired_sessions:
            self.clear_session(session_id)
    
    def is_group_chat_allowed(self, room_id: str) -> bool:
        """检查是否允许在指定群聊中使用"""
        # 检查群聊是否已启用AI功能
        if room_id not in self.enabled_rooms:
            logger.info(f"群 {room_id} 不在已启用群聊列表中，当前已启用群聊: {list(self.enabled_rooms)}")
            return False
            
        return True
        
    def is_admin(self, wxid: str) -> bool:
        """检查用户是否管理员"""
        return wxid in self.admin_wxids
    
    def toggle_group_ai(self, room_id: str, enable: bool = None) -> str:
        """切换群聊AI功能状态"""
        try:
            # 获取当前已启用的群聊列表
            enabled_rooms = list(self.group_config.get('enabled_rooms', []))  # 确保是列表
            
            # 记录原始状态
            was_enabled = room_id in self.enabled_rooms
            
            # 更新内存中的状态
            if enable is None:
                enable = not was_enabled
            
            if enable:
                if room_id not in self.enabled_rooms:
                    self.enabled_rooms.add(room_id)
                    if room_id not in enabled_rooms:
                        enabled_rooms.append(room_id)
                    logger.info(f"群聊 {room_id} 已开启AI对话功能")
            else:
                if room_id in self.enabled_rooms:
                    self.enabled_rooms.remove(room_id)
                    if room_id in enabled_rooms:
                        enabled_rooms.remove(room_id)
                    logger.info(f"群聊 {room_id} 已关闭AI对话功能")
            
            # 更新配置文件
            import yaml
            import os
            
            config_path = "config.yaml"
            if os.path.exists(config_path):
                # 读取当前配置
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                # 更新enabled_rooms
                if 'ai' in config and 'qwen' in config['ai'] and 'group_chat' in config['ai']['qwen']:
                    config['ai']['qwen']['group_chat']['enabled_rooms'] = enabled_rooms
                    
                    # 写回配置文件
                    with open(config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config, f, allow_unicode=True)
                        
                    # 同步更新group_config
                    self.group_config['enabled_rooms'] = enabled_rooms
                    
                    logger.info(f"已更新配置文件，当前已启用群聊: {enabled_rooms}")
            
            return "已开启本群AI对话功能" if enable else "已关闭本群AI对话功能"
            
        except Exception as e:
            logger.error(f"更新群聊AI功能状态失败: {e}", exc_info=True)
            return "操作失败，请查看日志"
    
    def toggle_private_chat(self, enable: bool) -> str:
        """切换私聊功能开关"""
        try:
            old_status = self.private_chat_enabled
            self.private_chat_enabled = enable
            
            if old_status != enable:
                status = "开启" if enable else "关闭"
                logger.info(f"AI私聊功能已{status}")
                
                # 检查白名单状态
                if enable and not self.private_chat_whitelist:
                    return f"已{status}私聊功能，但白名单为空，请先添加白名单用户"
                return f"已{status}私聊功能"
            else:
                status = "开启" if enable else "关闭"
                return f"私聊功能已经处于{status}状态"
        except Exception as e:
            logger.error(f"切换私聊功能失败: {e}")
            return "切换私聊功能失败"
    
    def is_private_chat_allowed(self, user_wxid: str) -> bool:
        """检查是否允许与指定用户进行私聊"""
        # 首先检查功能是否启用
        if not self.private_chat_enabled:
            logger.debug(f"私聊功能已禁用，拒绝用户 {user_wxid} 的请求")
            return False
            
        # 检查用户是否在白名单中
        is_allowed = user_wxid in self.private_chat_whitelist
        logger.debug(f"用户 {user_wxid} {'在' if is_allowed else '不在'}白名单中")
        return is_allowed
    
    def test_ai_function(self) -> str:
        """测试AI功能"""
        if not self.is_available():
            return "AI功能未正确配置，请检查API key和应用ID"
        
        try:
            # 检查API配置
            if not dashscope.api_key:
                return "未配置API key"
            if not dashscope.app_id:
                return "未配置应用ID"
            
            # 返回配置状态
            return (
                "AI功能配置检查:\n"
                f"• API Key: {'已配置 ✓' if dashscope.api_key else '未配置 ×'}\n"
                f"• 应用ID: {'已配置 ✓' if dashscope.app_id else '未配置 ×'}\n"
                f"• 模型: {self.model}\n"
                f"• 私聊功能: {'已启用 ✓' if self.private_chat_enabled else '已禁用 ×'}\n"
                f"• 群聊功能: {'已启用 ✓' if self.enabled_rooms else '已禁用 ×'}"
            )
            
        except Exception as e:
            logger.error(f"AI功能测试失败: {e}")
            return "AI功能测试失败，请查看日志"
    
    def add_to_whitelist(self, user_wxid: str) -> bool:
        """添加用户到白名单"""
        try:
            if user_wxid in self.private_chat_whitelist:
                logger.info(f"用户 {user_wxid} 已在白名单中")
                return False
            
            # 更新内存中的白名单
            new_whitelist = self.private_chat_whitelist.copy()
            new_whitelist.add(user_wxid)
            
            # 更新配置文件
            if self.update_whitelist_config(new_whitelist):
                logger.info(f"已添加用户 {user_wxid} 到私聊白名单")
                return True
            
            return False
        except Exception as e:
            logger.error(f"添加白名单失败: {e}")
            return False
    
    def remove_from_whitelist(self, user_wxid: str) -> bool:
        """从白名单移除用户"""
        try:
            if user_wxid not in self.private_chat_whitelist:
                logger.info(f"用户 {user_wxid} 不在白名单中")
                return False
            
            # 更新内存中的白名单
            new_whitelist = self.private_chat_whitelist.copy()
            new_whitelist.remove(user_wxid)
            
            # 更新配置文件
            if self.update_whitelist_config(new_whitelist):
                logger.info(f"已从私聊白名单移除用户 {user_wxid}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"移除白名单失败: {e}")
            return False
    
    def get_whitelist(self) -> set:
        """获取白名单列表"""
        return self.private_chat_whitelist.copy()
    
    def sync_whitelist_with_config(self):
        """同步白名单配置"""
        try:
            # 从配置中获取白名单
            whitelist = self.private_chat_config.get('whitelist', [])
            self.private_chat_whitelist = set(whitelist)
            
            # 记录同步结果
            if self.private_chat_whitelist:
                logger.info(f"已同步白名单: {', '.join(self.private_chat_whitelist)}")
            else:
                logger.warning("白名单为空")
                
            return True
        except Exception as e:
            logger.error(f"同步白名单失败: {e}")
            return False
    
    def update_whitelist_config(self, whitelist: set) -> bool:
        """更新白名单配置"""
        try:
            from ruamel.yaml import YAML
            yaml = YAML()
            yaml.preserve_quotes = True
            
            config_path = "config.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.load(f)
            
            # 更新配置中的白名单
            if 'ai' in config and 'qwen' in config['ai']:
                config['ai']['qwen']['private_chat']['whitelist'] = list(whitelist)
                
                # 写回配置文件
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f)
                
                # 同步内存中的白名单
                self.private_chat_whitelist = whitelist.copy()
                logger.info(f"已更新白名单配置: {list(whitelist)}")
                return True
                
            return False
        except Exception as e:
            logger.error(f"更新白名单配置失败: {e}")
            return False

def extract_message_content(wcf: Wcf, msg: WxMsg) -> Optional[str]:
    """
    提取消息内容
    
    Args:
        wcf: WeChatFerry 实例
        msg: 消息对象
        
    Returns:
        消息内容，如果是无效消息则返回 None
    """
    try:
        # 处理私聊消息
        if not msg.roomid:
            # 否则接返回消息内容
            return msg.content.strip()
            
        # 处理群聊消息
        if msg.roomid:
            # 如果命令，不在这里处理
            if msg.content.startswith('.'):
                return None
                
            # 直接返回原始消息内容，让handle_ai_chat处理
            return msg.content.strip()
            
        return None
        
    except Exception as e:
        logger.error(f"提取消息内容出错: {e}", exc_info=True)
        return None

async def handle_ai_chat(wcf: Wcf, msg: WxMsg, qwen: QwenChat) -> None:
    """处理AI聊天"""
    try:
        # 生成会话ID
        session_id = msg.roomid if msg.roomid else msg.sender
        content = msg.content.strip()
        
        # 如果是命令，直接返回
        if content.startswith('.'):
            return
        
        # 处理群聊消息
        if msg.roomid:
            # 检查是否@了机器人
            if not msg.is_at:
                return
            
            # 忽略@所有人的消息
            if "@所有人" in content:
                return
            
            # 获取机器人自己的ID
            self_wxid = wcf.get_self_wxid()
            at_text = f"@{wcf.get_alias_in_chatroom(self_wxid, msg.roomid) or self_wxid}"
            
            # 检查是否@了机器人
            if at_text not in content:
                return
            
            # 检查群聊是否在启用列表中
            if not qwen.is_group_chat_allowed(msg.roomid):
                wcf.send_text("本群AI功能未启用，请联系管理员使用.ai room on开启", msg.roomid)
                return
            
            # 移除@标记
            content = content.replace(at_text, "").strip()
            if not content:  # 如果只有@没有其他内容，也给出提示
                wcf.send_text("我在听，请说出您的问题", msg.roomid)
                return
        
        # 清理过期会话
        qwen.clean_expired_sessions()
        
        # 获取AI响应
        response = await qwen.get_response(session_id, content)
        
        if response:
            # 发送响应
            if msg.roomid:
                wcf.send_text(response, msg.roomid)
            else:
                wcf.send_text(response, msg.sender)
                
    except Exception as e:
        logger.error(f"处理AI聊天出错: {e}", exc_info=True)
        error_msg = "抱歉，处理消息时出现错误，请稍后重试"
        target = msg.roomid if msg.roomid else msg.sender
        wcf.send_text(error_msg, target) 