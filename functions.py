import logging
import random
from datetime import datetime
from typing import Tuple
from wcferry import Wcf, WxMsg
from dice_roller import dicehelp, format_reply_message
import json
import os

logger = logging.getLogger(__name__)

# 存储用户今日人品的字典
jrrp_cache = {}
jrrp_queried = {}

# 存储用户查询记录的字典
deck_cache = {}  # 用于缓存已加载的牌堆

def get_user_display_name(wcf: Wcf, wxid: str, room_id: str = None) -> str:
    """获取用户显示名称"""
    logger.debug(f"开始获取用户信息: wxid={wxid}, room_id={room_id}")
    
    try:
        if room_id:
            group_nickname = wcf.get_alias_in_chatroom(wxid, room_id)
            if group_nickname:
                return group_nickname
        
        friends = wcf.get_contacts()
        for friend in friends:
            if wxid == friend.get("wxid"):
                logger.debug(f"使用微信昵称: {friend['name']}")
                return friend['name']
        
        for groupid, group_users in wcf.group_users.items():
            if group_users.get(wxid) is not None:
                logger.debug(f"使用群成员昵称: {group_users[wxid]}")
                return group_users[wxid]
        
        logger.debug("无法获取用户名称，使用默认")
        return "骰子手"
        
    except Exception as e:
        logger.error(f"获取用户名称时出错: {e}")
        return "骰子手"

def handle_dicehelp_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.dicehelp命令"""
    try:
        help_text = dicehelp()
        logger.debug(f"生成骰子帮助信息: {help_text}")
        
        if msg.roomid:
            wcf.send_text(help_text, msg.roomid)
        else:
            wcf.send_text(help_text, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.dicehelp命令出错: {e}", exc_info=True)
        error_msg = "获取骰子帮助信息时出错"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

def get_today_rp(user_id: str) -> Tuple[int, bool]:
    """获取用户今日人品值"""
    today = datetime.now().strftime('%Y-%m-%d')
    cache_key = (user_id, today)
    
    if cache_key in jrrp_queried:
        return jrrp_cache[cache_key], True
    
    seed = f"{user_id}{today}"
    random.seed(seed)
    rp_value = random.randint(1, 100)
    
    jrrp_cache[cache_key] = rp_value
    jrrp_queried[cache_key] = True
    return rp_value, False

def get_rp_level(rp_value: int) -> str:
    """根据人品值获取对应评语"""
    if rp_value == 1:
        return "凶"
    elif 2 <= rp_value <= 19:
        return "末吉"
    elif 20 <= rp_value <= 39:
        return "小吉"
    elif 40 <= rp_value <= 59:
        return "中吉"
    elif 60 <= rp_value <= 79:
        return "吉"
    elif 80 <= rp_value <= 99:
        return "大吉"
    elif rp_value == 100:
        return "吉中吉"
    return "未知"

def handle_jrrp_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.jrrp命令"""
    try:
        nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
        rp_value, already_queried = get_today_rp(msg.sender)
        
        if already_queried:
            reply = "兄台今天已经算过啦，明日再来吧！"
        else:
            rp_level = get_rp_level(rp_value)
            reply = f"【{nickname}】今日人品：{rp_value} ({rp_level})"
        
        logger.debug(f"生成今日人品信息: {reply}")
        
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.jrrp命令出错: {e}", exc_info=True)
        error_msg = "获取今日人品时出错"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

def search_dnd_term(dnd_data: dict, keyword: str) -> str:
    """搜索D&D词条"""
    keyword = keyword.lower().strip()
    results = []
    
    logger.debug(f"开始搜索词条，关键词: '{keyword}'")
    
    for term, content in dnd_data.items():
        if isinstance(content, dict):
            for sub_term, sub_content in content.items():
                if keyword in sub_term.lower():
                    results.append(f"【{sub_term}】\n{sub_content}")
        elif keyword in term.lower():
            results.append(f"【{term}】\n{content}")
    
    if not results:
        return f"未找到与'{keyword}'相关的词条"
    
    return "\n\n".join(results[:3])

def handle_dnd_command(wcf: Wcf, msg: WxMsg, dnd_data: dict) -> None:
    """处理.dnd命令"""
    try:
        keyword = msg.content.split('.dnd', 1)[1].strip()
        
        if not keyword:
            reply = "请输入要查询的关键词，例如：.dnd 武器"
        else:
            reply = search_dnd_term(dnd_data, keyword)
        
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.dnd命令出错: {e}", exc_info=True)
        error_msg = "查询D&D词条时出错"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

# 抽卡相关函数
def flatten_deck(deck: dict) -> list:
    """将包含子条目的牌堆展平为单层列表"""
    flattened = []
    
    if isinstance(deck, list):
        return deck
    elif isinstance(deck, dict):
        for key, value in deck.items():
            if isinstance(value, (dict, list)):
                sub_items = flatten_deck(value)
                flattened.extend(sub_items)
            else:
                flattened.append(f"{key}: {value}")
    
    return flattened

def load_deck(deck_name: str, config: dict) -> list:
    """加载指定的牌堆"""
    try:
        if deck_name in deck_cache:
            return deck_cache[deck_name]
        
        deck_filename = config.get('decks', {}).get(deck_name)
        if not deck_filename:
            return []
        
        deck_path = config.get('files', {}).get('deck_path', 'decks')
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, deck_path, deck_filename)
        
        if not os.path.exists(file_path):
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_deck = json.load(f)
            deck = flatten_deck(raw_deck)
            deck_cache[deck_name] = deck
            return deck
            
    except Exception as e:
        logger.error(f"加载牌堆出错: {e}", exc_info=True)
        return []

def draw_cards(deck: list, count: int = 1) -> Tuple[list, int]:
    """从牌堆中抽取指定数量的卡牌"""
    deck_size = len(deck)
    if not deck:
        return [], 0
    
    count = min(count, deck_size)
    return random.sample(deck, count), deck_size

def handle_draw_command(wcf: Wcf, msg: WxMsg, config: dict) -> None:
    """处理.draw命令"""
    try:
        parts = msg.content.split('.draw', 1)[1].strip().split()
        if not parts:
            reply = "请指定要抽取的牌堆，例如：.draw dmt 1"
        else:
            deck_name = parts[0]
            count = 1
            
            if len(parts) > 1:
                try:
                    count = max(1, int(parts[1]))
                except ValueError:
                    count = 1
            
            deck = load_deck(deck_name, config)
            if not deck:
                reply = f"未找到牌堆: {deck_name}"
            else:
                cards, deck_size = draw_cards(deck, count)
                if not cards:
                    reply = "抽取卡牌失败"
                else:
                    nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
                    cards_text = "\n".join([f"- {card}" for card in cards])
                    deck_info = f"\n(牌堆共{deck_size}张)" + ("，已抽取全部可用卡牌" if count > deck_size else "")
                    reply = f"【{nickname}】从牌堆中抽取了 {len(cards)} 张卡牌：\n{cards_text}{deck_info}"
        
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.draw命令出错: {e}", exc_info=True)
        error_msg = "抽取卡牌时出错"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

def handle_drawhelp_command(wcf: Wcf, msg: WxMsg, config: dict) -> None:
    """处理.drawhelp命令"""
    try:
        decks_info = config.get('decks', {})
        if not decks_info:
            reply = "未配置任何牌堆。"
        else:
            deck_details = []
            for deck_name, deck_file in decks_info.items():
                deck = load_deck(deck_name, config)
                deck_size = len(deck)
                deck_details.append(f"{deck_name} ({deck_size}张) - 文件: {deck_file}")
            
            deck_list = "\n".join(deck_details)
            reply = f"可用牌堆列表：\n{deck_list}\n\n使用示例：\n.draw 牌堆名 数量\n例如：.draw dmt 1"
        
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.drawhelp命令出错: {e}", exc_info=True)
        error_msg = "获取牌堆信息时出错"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

def handle_sys_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.sys命令"""
    try:
        status_info = "机器人状态: 正常运行\n"
        
        if msg.roomid:
            wcf.send_text(status_info, msg.roomid)
        else:
            wcf.send_text(status_info, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.sys命令出错: {e}", exc_info=True)
        error_msg = "获取状态信息时出错"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender) 