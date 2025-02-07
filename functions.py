import logging
import random
from datetime import datetime
from typing import Tuple
from wcferry import Wcf, WxMsg
from dice_roller import dicehelp, format_reply_message
import json
import os
import hashlib

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
        # 判断是否为私聊（wxid 和 room_id 相同）
        if room_id and wxid == room_id:
            room_id = None  # 重置 room_id，确保后续逻辑正确处理私聊
            logger.debug("检测到私聊消息")
        
        # 如果是群聊消息
        if room_id:
            group_nickname = wcf.get_alias_in_chatroom(wxid, room_id)
            if group_nickname:
                logger.debug(f"使用群昵称: {group_nickname}")
                return group_nickname
        
        # 获取好友列表
        friends = wcf.get_contacts()
        for friend in friends:
            if wxid == friend.get("wxid"):
                logger.debug(f"使用微信昵称: {friend['name']}")
                return friend['name']
        
        # 如果是群成员
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

def handle_jrrp_command(wcf: Wcf, msg: WxMsg, **kwargs) -> None:
    """处理今日人品命令"""
    try:
        # 获取用户ID和日期
        user_id = msg.sender
        today = datetime.now().strftime('%Y%m%d')
        
        # 生成种子并计算人品值
        seed = f"{user_id}{today}".encode()
        random.seed(hashlib.md5(seed).hexdigest())
        value = random.randint(1, 100)
        
        # 根据人品值判断凶吉和应对建议
        if value >= 90:
            result = "大吉"
            advice = random.choice([
                "今日诸事皆宜，可大胆行事，必有所获",
                "福星高照，宜把握机会，开展新事业",
                "运势极佳，适合冒险尝试，有意外之喜",
                "吉星临门，适合重要决策，贵人相助",
                "今日必有好事发生，宜主动出击"
            ])
        elif value >= 75:
            result = "中吉"
            advice = random.choice([
                "运势不错，适合社交活动，可结识良缘",
                "宜与人合作，能事半功倍，有贵人相助",
                "工作顺利，适合谈判签约，易得好结果",
                "可尝试新事物，有较大收获机会",
                "适合外出活动，可能遇到好机遇"
            ])
        elif value >= 60:
            result = "小吉"
            advice = random.choice([
                "平稳顺遂，按部就班即可，不必强求",
                "小事可为，大事需谋，循序渐进为宜",
                "适合处理日常事务，不��冒进",
                "宜与友人小聚，闲谈论事，有小收获",
                "保持平常心，做好当下事，自有回报"
            ])
        elif value >= 40:
            result = "平"
            advice = random.choice([
                "平平淡淡，宜低调行事，顺其自然",
                "不宜激进，稳扎稳打，循序渐进",
                "适合整理思绪，规划未来，暂避风头",
                "宜修身养性，读书充电，等待机会",
                "平常心对待，不喜不忧，守正待时"
            ])
        elif value >= 25:
            result = "小凶"
            advice = random.choice([
                "诸事需谨慎，不宜轻举妄动，避免冲动",
                "小心口舌是非，言多必失，沉默是金",
                "投资需谨慎，易有小损失，量力而行",
                "避免争执冲突，退一步海阔天空",
                "宜修身养性，暂避风头，等待时机"
            ])
        elif value >= 10:
            result = "凶"
            advice = random.choice([
                "诸事不宜，宜闭门思过，避免外出",
                "慎重决策，避免冒险，不宜轻举妄动",
                "恐有口舌是非，远离是非之地为上",
                "财运不佳，不宜投资，守财为上",
                "小心小人暗算，谨言慎行为要"
            ])
        else:
            result = "大凶"
            advice = random.choice([
                "最好闭门不出，避免一切冒险行为",
                "宜静不宜动，避免一切重要决策",
                "谨防小人暗算，避免与人结怨",
                "恐有血光之灾，切勿轻举妄动",
                "诸事不顺，不如安心休息，等待转机"
            ])
        
        # 获取用户昵称
        nickname = get_user_display_name(wcf, user_id, msg.roomid)
        
        # 组织返回消息
        reply = f"{nickname} 今日运势：{result}\n{advice}"
        
        # 发送消息
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理今日人品命令出错: {e}", exc_info=True)
        if msg.roomid:
            wcf.send_text("处理命令时出错，请稍后重试", msg.roomid)
        else:
            wcf.send_text("处理命令时出错，请稍后重试", msg.sender)

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
            logger.debug(f"使用缓存的牌堆: {deck_name}")
            return deck_cache[deck_name]
        
        deck_filename = config.get('decks', {}).get(deck_name)
        logger.debug(f"尝试加载牌堆文件: {deck_name} -> {deck_filename}")
        if not deck_filename:
            logger.error(f"未找到牌堆配置: {deck_name}")
            return []
        
        deck_path = config.get('files', {}).get('deck_path', 'decks')
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, deck_path, deck_filename)
        logger.debug(f"完整的牌���文件路径: {file_path}")
        
        if not os.path.exists(file_path):
            # 尝试txt格式
            txt_path = os.path.splitext(file_path)[0] + '.txt'
            if os.path.exists(txt_path):
                file_path = txt_path
            else:
                logger.error(f"牌堆文件不存在: {file_path} 或 {txt_path}")
                return []
        
        # 根据文件扩展名选择加载方式
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_deck = json.load(f)
                logger.debug(f"成功加载JSON牌堆文件: {deck_name}, 原始内容: {raw_deck}")
                deck = flatten_deck(raw_deck)
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                # 每行作为一个条目
                deck = []
                for line in f:
                    line = line.strip()
                    if line:
                        # 如果行包含冒号，保持原格式；否则只使用行内容
                        if ':' in line:
                            deck.append(line)
                        else:
                            deck.append(f"{line}: {line}")
                logger.debug(f"成功加载TXT牌堆文件: {deck_name}, 内容: {deck}")
        else:
            logger.error(f"不支持的牌堆文件格式: {ext}")
            return []

        logger.debug(f"展平后的牌堆内容: {deck}")
        deck_cache[deck_name] = deck
        return deck
            
    except Exception as e:
        logger.error(f"加载牌堆出错: {e}", exc_info=True)
        return []

def draw_cards(deck: list, count: int = 1) -> Tuple[list, int]:
    """从牌堆中抽取指定数量的卡牌"""
    deck_size = len(deck)
    logger.debug(f"牌堆大小: {deck_size}, 请求抽取数量: {count}")
    if not deck:
        logger.error("牌堆为空")
        return [], 0
    
    count = min(count, deck_size)
    logger.debug(f"实际抽取数量: {count}")
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
                    # 检查文件扩展名
                    deck_filename = config.get('decks', {}).get(deck_name, '')
                    is_txt = deck_filename.lower().endswith('.txt')
                    
                    if is_txt:
                        # txt格式只显示卡牌名称
                        cards_text = "\n".join([f"- {card.split(':', 1)[0].strip()}" for card in cards])
                    else:
                        # json格式显示完整内容
                        cards_text = "\n".join([f"- {card}" for card in cards])
                        
                    deck_info = f"\n(牌堆共{deck_size}张)" + ("，已抽取全部可用卡牌" if count > deck_size else "")
                    reply = f"【{nickname}】从牌堆中抽取了 {len(cards)} 张卡牌：\n{cards_text}{deck_info}"
                    
                    # 如果是108将牌堆，发送对应图片
                    if deck_name == "108bro":
                        # 获取decks目录路径
                        deck_path = config.get('files', {}).get('deck_path', 'decks')
                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        pics_path = os.path.join(current_dir, deck_path, "pics")
                        
                        for card in cards:
                            card_name = card.split(":")[0].strip()  # 获取卡牌名称
                            # 移除卡牌名称中的下划线
                            card_name_no_underscore = card_name.replace("_", "")
                            
                            # 遍历目录查找匹配的图片
                            found = False
                            pic_path = os.path.join(pics_path, f"{card_name}.jpg")  # 默认路径，用于日志
                            if os.path.exists(pics_path):
                                for pic_file in os.listdir(pics_path):
                                    if pic_file.lower().endswith('.jpg'):
                                        # 移除图片文件名中的下划线和扩展名进行比较
                                        pic_name = os.path.splitext(pic_file)[0].replace("_", "")
                                        if pic_name == card_name_no_underscore:
                                            pic_path = os.path.join(pics_path, pic_file)
                                            if msg.roomid:
                                                wcf.send_image(pic_path, msg.roomid)
                                            else:
                                                wcf.send_image(pic_path, msg.sender)
                                            found = True
                                            break
                            if not found:
                                logger.debug(f"未找到对应图片: {card_name}")
        
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
            reply = "未配置任何牌��。"
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