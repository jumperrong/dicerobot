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
        
        # 确保帮助信息以TRPG风格展示
        if not help_text.startswith("🎲"):
            help_text = f"""🎲 骰子指令详细说明:
    
🎯 基础指令:
• .r 或 r 开头，如 .rd20、rd6
• 省略骰子数量时默认为1，如 d20 = 1d20

📊 基础表达式:
• NdS     掷N个S面骰，如 2d6
• d20     掷1个20面骰
• 2d8+3   掷2个8面骰并加3

🎮 高级表达式:
• 优势投掷:  d20a 或 d20a3 (a后数字为投掷次数，默认2次)
• 劣势投掷:  d20p 或 d20p3 (p后数字为投掷次数，默认2次)
• 重复投掷:  d4:d6 (用d4的结果决定投掷d6的次数)
• 带括号重复: d4:(d8+2) (重复投掷括号内的完整表达式)
• 复合运算:  d8*(d4+2) (支持加减乘除和括号)

📝 示例说明:
1. d4:d8
   - 先投d4获得次数N
   - 重复投掷d8共N次
   - 计算N次结果的总和

2. d4:d8+2
   - 先投d4获得次数N
   - 重复投掷d8共N次得到总和
   - 最后加上2

3. d4:(d8+2)
   - 先投d4获得次数N
   - 重复计算(d8+2)共N次
   - 计算N次结果的总和

4. d8*(d4+2)
   - 先计算d8的结果
   - 再计算(d4+2)的结果
   - 将两个结果相乘

⚠️ 注意事项:
• 表达式中请勿包含空格
• 运算符优先级: () > d > a/p > : > */ > +-
• 括号内的表达式会作为一个整体计算
• 支持的运算符: + - * / : ( )
• 数值限制: 骰子数量≤100，面数≤1000"""
            
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
    """处理今日人品命令，从64卦中抽取一卦"""
    try:
        # 获取用户ID和日期
        user_id = msg.sender
        today = datetime.now().strftime('%Y-%m-%d')
        cache_key = (user_id, today)
        
        # 检查用户今天是否已经卜过卦
        if cache_key in jrrp_queried:
            # 用户今天已经卜过卦，随机选择一句诗句回复
            poetic_replies = [
                "机缘已尽，星辰待转，请君明日再续前缘。",
                "日晷影斜，天机暂隐，且待明朝再启玄章。",
                "更漏已尽，卦象归寂，明日重开天地局。",
                "檐前风止，卜辞封卷，留待寅时续新篇。",
                "炉香烬冷，天命难窥，请乘晨露复叩门。",
                "月轮沉西，紫微星隐，缘起缘落待曦光。",
                "云篆收笔，乾坤未语，明朝再问山海经。",
                "茶凉三盏，卦盘锁钥，重沏新茗候君临。",
                "棋局终散，阴阳难测，且执白子约晓钟。"
            ]
            
            # 随机选择一句
            reply = f"🕰️ {random.choice(poetic_replies)}"
            
            if msg.roomid:
                wcf.send_text(reply, msg.roomid)
            else:
                wcf.send_text(reply, msg.sender)
            return
        
        # 标记用户今天已经卜过卦
        jrrp_queried[cache_key] = True
        
        # 生成种子
        seed = f"{user_id}{today}".encode()
        random.seed(hashlib.md5(seed).hexdigest())
        
        # 读取64卦数据
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, "jrrp", "64.json")
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                hexagrams = json.load(f)
                
            # 随机选择一卦
            hexagram_name = random.choice(list(hexagrams.keys()))
            hexagram = hexagrams[hexagram_name]
            
            # 缓存卦象
            jrrp_cache[cache_key] = hexagram_name
            
            # 获取卦象图片路径
            image_path = os.path.join(current_dir, "jrrp", f"{hexagram_name}.jpg")
            
            # 获取用户昵称
            nickname = get_user_display_name(wcf, user_id, msg.roomid)
            
            # 组织返回消息
            reply = f"""🔮 今日卜卦：
👤 {nickname}
📅 {datetime.now().strftime('%Y年%m月%d日')}
🏮 {hexagram['title']}
⭐ 卦象评分：{hexagram['level']}
📜 卦辞诗句：{hexagram['poem']}
📝 解释：{hexagram['explanation']}"""
            
            # 发送消息和图片
            if msg.roomid:
                if os.path.exists(image_path):
                    wcf.send_image(image_path, msg.roomid)
                wcf.send_text(reply, msg.roomid)
            else:
                if os.path.exists(image_path):
                    wcf.send_image(image_path, msg.sender)
                wcf.send_text(reply, msg.sender)
                
        except FileNotFoundError:
            logger.error(f"64卦数据文件未找到: {json_path}")
            default_reply = "卦象数据未找到，请联系管理员。"
            if msg.roomid:
                wcf.send_text(default_reply, msg.roomid)
            else:
                wcf.send_text(default_reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理今日卜卦命令出错: {e}", exc_info=True)
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
                    results.append(f"📚 【{sub_term}】\n{sub_content}")
        elif keyword in term.lower():
            results.append(f"📚 【{term}】\n{sub_content}")
    
    if not results:
        return f"❌ 未找到与'{keyword}'相关的词条"
    
    return "\n\n".join(results[:3])

def handle_dnd_command(wcf: Wcf, msg: WxMsg, dnd_data: dict) -> None:
    """处理.dnd命令"""
    try:
        keyword = msg.content.split('.dnd', 1)[1].strip()
        
        if not keyword:
            reply = """🎲 D&D规则查询
请输入要查询的关键词，例如：
• .dnd 武器
• .dnd 法术
• .dnd 职业
• .dnd 种族"""
        else:
            # 获取用户昵称
            nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
            
            # 进行查询并格式化结果
            result = search_dnd_term(dnd_data, keyword)
            reply = f"""🔍 D&D规则查询:
👤 {nickname}
🔎 关键词: {keyword}

{result}"""
        
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.dnd命令出错: {e}", exc_info=True)
        error_msg = "❌ 查询D&D词条时出错"
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
        logger.debug(f"完整的牌堆文件路径: {file_path}")
        
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
            reply = """🎴 抽卡命令说明
请指定要抽取的牌堆，例如：
• .draw dmt 1   - 从大密十牌堆抽1张
• .draw tarot 3 - 从塔罗牌堆抽3张
使用 .drawhelp 查看可用牌堆列表"""
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
                reply = f"❌ 未找到牌堆: {deck_name}"
            else:
                cards, deck_size = draw_cards(deck, count)
                if not cards:
                    reply = "❌ 抽取卡牌失败"
                else:
                    nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
                    # 检查文件扩展名
                    deck_filename = config.get('decks', {}).get(deck_name, '')
                    is_txt = deck_filename.lower().endswith('.txt')
                    
                    # 添加牌堆名称的显示
                    deck_display_name = config.get('deck_names', {}).get(deck_name, deck_name.upper())
                    
                    if is_txt:
                        # txt格式只显示卡牌名称，添加图标
                        cards_text = "\n".join([f"🎴 {card.split(':', 1)[0].strip()}" for card in cards])
                    else:
                        # json格式显示完整内容，添加图标
                        cards_text = "\n".join([f"🎴 {card}" for card in cards])
                        
                    deck_info = f"\n📊 牌堆共{deck_size}张" + ("，已抽取全部可用卡牌" if count >= deck_size else "")
                    reply = f"""🎲 抽卡结果:
👤 {nickname} 
🌟 牌堆: {deck_display_name}
📝 抽取: {len(cards)}张

{cards_text}
{deck_info}"""
                    
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.draw命令出错: {e}", exc_info=True)
        error_msg = "❌ 抽卡命令执行出错，请稍后重试"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

def handle_drawhelp_command(wcf: Wcf, msg: WxMsg, config: dict) -> None:
    """处理.drawhelp命令"""
    try:
        deck_configs = config.get('decks', {})
        if not deck_configs:
            reply = "❌ 未找到牌堆配置"
        else:
            # 尝试获取牌堆的描述信息
            deck_descs = config.get('deck_descriptions', {})
            
            lines = ["🎴 可用牌堆列表:"]
            for name, filename in deck_configs.items():
                # 获取牌堆描述
                desc = deck_descs.get(name, "")
                if desc:
                    lines.append(f"• {name} - {desc}")
                else:
                    lines.append(f"• {name}")
            
            lines.append("\n📝 使用方法:")
            lines.append("• .draw <牌堆名> [抽取数量]")
            lines.append("• 例如: .draw dmt 3")
                
            reply = "\n".join(lines)
                
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.drawhelp命令出错: {e}", exc_info=True)
        error_msg = "❌ 获取牌堆帮助信息失败"
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