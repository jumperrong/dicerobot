import logging
import time
from queue import Empty
from wcferry import Wcf, WxMsg
from dice_roller import process_roll_command, dicehelp, format_reply_message
import random
from datetime import datetime
from typing import Tuple
import re
import json
import os
import yaml

# 在文件开头，导入模块后添加基础logger配置
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

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

# 存储用户今日人品的字典
# 格式: {(user_id, date_str): rp_value}
jrrp_cache = {}

# 存储用户查询记录的
# 格式: {(user_id, date_str): True}
jrrp_queried = {}

# 在其他全局变量定义后添加
DND_DATA_FILE = "DND5E23_4_2.json"
dnd_data = {}

# 在全局变量区域添加
deck_cache = {}  # 用于缓存已加载的牌堆

def flatten_deck(deck: dict) -> list:
    """将包含子条目的牌堆展平为单层列表
    
    Args:
        deck: 牌堆字典或列表
    
    Returns:
        list: 展平后的卡牌列表
    """
    flattened = []
    
    if isinstance(deck, list):
        return deck
    elif isinstance(deck, dict):
        for key, value in deck.items():
            if isinstance(value, (dict, list)):
                # 递归处理子条目
                sub_items = flatten_deck(value)
                flattened.extend(sub_items)
            else:
                flattened.append(f"{key}: {value}")
    
    return flattened

def load_deck(deck_name: str, config: dict) -> list:
    """加载指定的牌堆
    
    Args:
        deck_name: 牌堆的配置名称
        config: 配置字典
    
    Returns:
        list: 牌堆内容列表
    """
    try:
        # 检查缓存
        if deck_name in deck_cache:
            logger.debug(f"从缓存加载牌堆: {deck_name}")
            return deck_cache[deck_name]
        
        # 获取牌堆文件名
        deck_filename = config.get('decks', {}).get(deck_name)
        if not deck_filename:
            logger.error(f"未找到牌堆配置: {deck_name}")
            return []
        
        # 构建完整路径
        deck_path = config.get('files', {}).get('deck_path', 'decks')
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, deck_path, deck_filename)
        
        logger.debug(f"尝试加载牌堆文件: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"牌堆文件不存在: {file_path}")
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_deck = json.load(f)
            # 展平牌堆
            deck = flatten_deck(raw_deck)
            logger.debug(f"成功加载牌堆 {deck_name}, 包含 {len(deck)} 张卡牌")
            
            # 缓存牌堆
            deck_cache[deck_name] = deck
            return deck
            
    except Exception as e:
        logger.error(f"加载牌堆出错: {e}", exc_info=True)
        return []

def draw_cards(deck: list, count: int = 1) -> Tuple[list, int]:
    """从牌堆中抽取指定数量的卡牌
    
    Args:
        deck: 牌堆列表
        count: 要抽取卡牌数量
    
    Returns:
        Tuple[list, int]: (抽取的卡牌列表, 牌堆总数)
    """
    deck_size = len(deck)
    if not deck:
        return [], 0
    
    # 确保不会抽取超过牌堆大小的数量
    count = min(count, deck_size)
    return random.sample(deck, count), deck_size

def format_card_text(card: str) -> str:
    """格式化卡牌文本
    
    Args:
        card: 原始卡牌文本
    
    Returns:
        str: 格式化后的文本
    """
    # 如果卡牌文本已经包含分隔符（如"："），直接返回
    if ': ' in card:
        return card
    return card

def handle_draw_command(wcf: Wcf, msg: WxMsg, config: dict) -> None:
    """处理.draw命令"""
    try:
        # 解析命令
        parts = msg.content.split('.draw', 1)[1].strip().split()
        if not parts:
            reply = "请指定要抽取的牌堆，例如：.draw dmt 1"
            logger.debug("未指定牌堆名称")
        else:
            deck_name = parts[0]
            count = 1  # 默认抽取数量
            
            # 如果指定了抽取数量
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                    if count < 1:
                        count = 1
                except ValueError:
                    count = 1
            
            logger.debug(f"抽取牌堆: {deck_name}, 请求数量: {count}")
            
            # 加载牌堆
            deck = load_deck(deck_name, config)
            if not deck:
                reply = f"未找到牌堆: {deck_name}"
            else:
                # 抽取卡牌
                cards, deck_size = draw_cards(deck, count)
                if not cards:
                    reply = "抽取卡牌失败"
                else:
                    # 获取用户显示名称
                    nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
                    # 格式化结果
                    cards_text = "\n".join([f"- {format_card_text(card)}" for card in cards])
                    
                    # 根据抽取情况生成不同的提示
                    if count > deck_size:
                        deck_info = f"\n(牌堆共{deck_size}张，已抽取全部可用卡牌)"
                    else:
                        deck_info = f"\n(牌堆共{deck_size}张)"
                    
                    reply = f"【{nickname}】从牌堆中抽取了 {len(cards)} 张卡牌：\n{cards_text}{deck_info}"
        
        logger.debug(f"抽卡结果: {reply}")
        
        # 发送回复
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.draw命令出错: {e}", exc_info=True)
        error_msg = "抽取卡牌时出错，请稍后再试"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

# 配置日志
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
        logger.debug(f"尝试加载配置文件: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            logger.debug(f"成功加载置件: {config}")
            return config
    except Exception as e:
        logger.error(f"加载配置文件时出错: {e}", exc_info=True)
        return {}

def load_dnd_data(file_name: str) -> dict:
    """加载D&D数据文件"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, file_name)
        logger.debug(f"尝试加载D&D数据文件: {file_path}")
        
        if os.path.exists(file_path):
            logger.debug("文件存在，开始读取")
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"成功加载数据，词条数: {len(data)}")
                return data
        else:
            logger.error(f"文件不存在: {file_path}")
            return {}
    except Exception as e:
        logger.error(f"加载文件时出错: {e}", exc_info=True)
        return {}

def search_dnd_term(dnd_data: dict, keyword: str) -> str:
    """搜索D&D词条"""
    keyword = keyword.lower().strip()
    results = []
    
    logger.debug(f"开始搜索词条，关键词: '{keyword}'")
    logger.debug(f"当前数据库中共有 {len(dnd_data)} 个词条")
    
    for term, content in dnd_data.items():
        logger.debug(f"正在比条: '{term.lower()}' 与关键词: '{keyword}'")
        if isinstance(content, dict):
            # 如果内容是字典，递归搜索
            for sub_term, sub_content in content.items():
                logger.debug(f"正在比较词条: '{sub_term.lower()}' 与关键词: '{keyword}'")
                if keyword in sub_term.lower():
                    logger.debug(f"找到匹配子词条: {sub_term}")
                    results.append(f"【{sub_term}】\n{sub_content}")
        elif keyword in term.lower():
            logger.debug(f"找到匹配词条: {term}")
            results.append(f"【{term}】\n{content}")
    
    if not results:
        logger.debug(f"未找到与关键词 '{keyword}' 相关的词条")
        return f"未找到与'{keyword}'相关的词条"
    
    logger.debug(f"共找到 {len(results)} 个匹配词条")
    return "\n\n".join(results[:3])

def get_user_display_name(wcf: Wcf, wxid: str, room_id: str = None) -> str:
    """获取用户显示名称"""
    logger.debug(f"开始获取用户信息: wxid={wxid}, room_id={room_id}")
    
    try:
        if room_id:
            # 群聊消息
            group_nickname = wcf.get_alias_in_chatroom(wxid, room_id)
            if group_nickname:
                return group_nickname
        
        # 取用信息
        friends = wcf.get_contacts()
        for friend in friends:
            if wxid == friend.get("wxid"):
                logger.debug(f"使用微信昵称: {friend['name']}")
                return friend['name']
        
        # 群聊成员获取
        for groupid, group_users in wcf.group_users.items():
            if group_users.get(wxid) is not None:
                logger.debug(f"使用群成员昵称: {group_users[wxid]}")
                return group_users[wxid]
        
        # 如果获取失败，返回默认名称
        logger.debug("无法获取用户名称，使用默认")
        return "骰子手"
        
    except Exception as e:
        logger.error(f"获取用户名称时出错: {e}")
        return "骰子手"

def get_today_rp(user_id: str) -> Tuple[int, bool]:
    """获取用户今日人品值
    
    Returns:
        Tuple[int, bool]: (人品值, 是否已经查询过)
    """
    today = datetime.now().strftime('%Y-%m-%d')
    cache_key = (user_id, today)
    
    # 检查是否已查询过
    if cache_key in jrrp_queried:
        return jrrp_cache[cache_key], True
    
    # 使用用户ID和日期作为随机种子
    seed = f"{user_id}{today}"
    random.seed(seed)
    rp_value = random.randint(1, 100)
    
    # 缓存结果
    jrrp_cache[cache_key] = rp_value
    jrrp_queried[cache_key] = True
    return rp_value, False

def handle_roll_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理骰子命令"""
    try:
        command = msg.content.split('.r', 1)[1].strip()
        logger.debug(f"处理骰子命令: {command}")
        
        roll_results, result = process_roll_command(command)
        
        # 获取用户显示名称
        nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
        
        # 用 dice_roller 中的函数格式化回复消息
        reply = format_reply_message(nickname, roll_results, result)
        
        logger.debug(f"生成回复消息: {reply}")
        
        # 发送回复
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理骰子命令出错: {e}", exc_info=True)
        if msg.roomid:
            wcf.send_text("处理命令时出错，请使用 .help 查看帮助", msg.roomid)
        else:
            wcf.send_text("处理命令时出错，请使用 .help 查看帮助", msg.sender)

def handle_help_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.help命令，显示帮助信息"""
    try:
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

        logger.debug(f"生成帮助信息: {help_text}")
        
        # 发送帮助信息
        if msg.roomid:
            wcf.send_text(help_text, msg.roomid)
        else:
            wcf.send_text(help_text, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.help命令出错: {e}", exc_info=True)
        if msg.roomid:
            wcf.send_text("获取帮助信息时出错", msg.roomid)
        else:
            wcf.send_text("获取帮助信息时出错", msg.sender)

def handle_sys_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.sys命令，显示机器人状态"""
    try:
        # 假设我们有一些状态信息可以显示
        status_info = "机器人状态: 正常运行\n"  # 这里可以添加更多状态信息
        logger.debug(f"生成状态信息: {status_info}")
        
        # 发送状态信息
        if msg.roomid:
            wcf.send_text(status_info, msg.roomid)
        else:
            wcf.send_text(status_info, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.sys命令出错: {e}", exc_info=True)
        if msg.roomid:
            wcf.send_text("获取状态信息时出错", msg.roomid)
        else:
            wcf.send_text("获取状态信息时出错", msg.sender)

def handle_jrrp_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.jrrp命令，显示今日人品"""
    try:
        # 获取用户显示名称
        nickname = get_user_display_name(wcf, msg.sender, msg.roomid)
        
        # 获取今日人品值和查询状态
        rp_value, already_queried = get_today_rp(msg.sender)
        
        # 生成回复消息
        if already_queried:
            reply = "兄台今天已经算过啦，明日再来吧！"
        else:
            reply = f"【{nickname}】今日人品：{rp_value}"
            
        logger.debug(f"生成今日人品信息: {reply}")
        
        # 发送回复
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.jrrp命令出错: {e}", exc_info=True)
        if msg.roomid:
            wcf.send_text("获取今日人品时出错", msg.roomid)
        else:
            wcf.send_text("获取今日人品时出错", msg.sender)

def handle_dicehelp_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.dicehelp命令，显示骰子帮助信息"""
    try:
        help_text = dicehelp()
        logger.debug(f"���成骰子帮助信息: {help_text}")
        
        # 发送帮助信息
        if msg.roomid:
            wcf.send_text(help_text, msg.roomid)
        else:
            wcf.send_text(help_text, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.dicehelp命令出错: {e}", exc_info=True)
        if msg.roomid:
            wcf.send_text("获取骰子帮助信息时出错", msg.roomid)
        else:
            wcf.send_text("获取骰子帮助信息时出错", msg.sender)

def handle_dnd_command(wcf: Wcf, msg: WxMsg) -> None:
    """处理.dnd命令，查询D&D词条"""
    try:
        # 提取搜索关键词
        keyword = msg.content.split('.dnd', 1)[1].strip()
        logger.debug(f"提取的关键词: '{keyword}'")
        logger.debug(f"dnd_data类型: {type(dnd_data)}, 数据量: {len(dnd_data)}")
        
        if not keyword:
            reply = "请输入要查询的关键词，例如：.dnd 武器"
            logger.debug("未输入关键词")
        else:
            reply = search_dnd_term(dnd_data, keyword)
            logger.debug(f"D&D查询结果: {reply[:100]}...")  # 只记录前100个字
        
        # 发送回复
        if msg.roomid:
            logger.debug(f"发送到群聊: {msg.roomid}")
            wcf.send_text(reply, msg.roomid)
        else:
            logger.debug(f"发送到私聊: {msg.sender}")
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.dnd命令出错: {e}", exc_info=True)
        error_msg = "查询D&D词条时出错，请稍后再试"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

def handle_drawhelp_command(wcf: Wcf, msg: WxMsg, config: dict) -> None:
    """处理.drawhelp命令，显示牌堆信息和使用示例"""
    try:
        decks_info = config.get('decks', {})
        if not decks_info:
            reply = "未配置任何牌堆。"
            logger.debug("未找到牌堆配置")
        else:
            deck_details = []
            for deck_name, deck_file in decks_info.items():
                # 加载牌堆以获取张数
                deck = load_deck(deck_name, config)
                deck_size = len(deck)
                deck_details.append(f"{deck_name} ({deck_size}张) - 文件: {deck_file}")
            
            deck_list = "\n".join(deck_details)
            reply = f"可用牌堆列表：\n{deck_list}\n\n使用示例：\n.draw 牌堆名 数量\n例如：.draw dmt 1"
        
        logger.debug(f"生成.drawhelp信���: {reply}")
        
        # 发送回复
        if msg.roomid:
            wcf.send_text(reply, msg.roomid)
        else:
            wcf.send_text(reply, msg.sender)
            
    except Exception as e:
        logger.error(f"处理.drawhelp命令出错: {e}", exc_info=True)
        error_msg = "获取牌堆信息时出错，请稍后再试"
        if msg.roomid:
            wcf.send_text(error_msg, msg.roomid)
        else:
            wcf.send_text(error_msg, msg.sender)

def handle_message(wcf: Wcf, msg: WxMsg, config: dict) -> None:
    """处理接收到的消息"""
    # 获取消息显示配置
    msg_config = config.get('message_display', {})
    
    # 获取消息类型描述
    msg_type_desc = MSG_TYPES.get(msg.type, f"未知消息类型({msg.type})")
    
    # 检查是否应该显示该类型的消息
    should_log = msg_config.get(f'type_{msg.type}', False)
    
    # 准备日志内容
    if should_log:
        log_content = msg.content if msg.type == 1 else f"[{msg_type_desc}]"
        sender_name = get_user_display_name(wcf, msg.sender, msg.roomid)
        chat_type = "群聊" if msg.roomid else "私聊"
        logger.debug(f"[{chat_type}] [{msg_type_desc}] {sender_name}: {log_content}")

    # 处理命令消息
    if msg.type == 1 and msg.content.startswith('.'):  # 只处理文本命令
        if msg.content.startswith('.drawhelp'):  # 将 .drawhelp 的检查移到最前面
            logger.debug("识别为抽卡帮助命令")
            handle_drawhelp_command(wcf, msg, config)
        elif msg.content.startswith('.r'):
            logger.debug("识别为骰子命令")
            handle_roll_command(wcf, msg)
        elif msg.content.startswith('.help'):
            logger.debug("识别为帮助命令")
            handle_help_command(wcf, msg)
        elif msg.content.startswith('.sys'):
            logger.debug("识别为系统命令")
            handle_sys_command(wcf, msg)
        elif msg.content.startswith('.jrrp'):
            logger.debug("识别为今日人品命令")
            handle_jrrp_command(wcf, msg)
        elif msg.content.startswith('.dnd'):
            logger.debug("识别为D&D查询命令")
            handle_dnd_command(wcf, msg)
        elif msg.content.startswith('.dicehelp'):
            logger.debug("识别为骰子帮助命令")
            handle_dicehelp_command(wcf, msg)
        elif msg.content.startswith('.draw'):  # 将 .draw 的检查移到后面
            logger.debug("识别为抽卡命令")
            handle_draw_command(wcf, msg, config)
        else:
            logger.debug(f"未识别的命令: {msg.content}")

def main():
    """主函数"""
    global wcf, dnd_data
    
    # 加载配置
    config = load_config()
    setup_logging(config)
    
    wcf = Wcf()
    logger.info("正在启动骰子机器人...")
    
    try:
        logger.debug("初始化 WCF 对象完成")
        
        # 使用配置文件中的路径
        dnd_data_file = config.get('files', {}).get('dnd_data', 'DND5E23_4_2.json')
        dnd_data = load_dnd_data(dnd_data_file)
        logger.debug(f"加载D&D数据完成，数据量: {len(dnd_data)}")
        
        if not dnd_data:
            logger.error(f"D&D数据加载失败或为空，文件: {dnd_data_file}")
        
        logger.info("正在启用消息接收功能...")
        wcf.enable_receiving_msg()
        
        retry_count = 0
        max_retries = 5
        while not wcf.is_receiving_msg() and retry_count < max_retries:
            retry_count += 1
            logger.debug(f"检查消息接收状态: 第 {retry_count} 次尝试")
            logger.info(f"等待消息接收功能启动... ({retry_count}/{max_retries})")
            time.sleep(1)
        
        if not wcf.is_receiving_msg():
            logger.error("消息接收功能启动失败")
            return
            
        logger.info("骰子机器人已启动，开始接收消息")
        logger.info("支持的命令: .r (骰子指令), .help (帮助信息), .sys (机器人状态), .jrrp (今日人品), .dnd (D&D查询)")
        logger.debug("进入主循环")
        
        # 持续读取消息
        while True:
            try:
                # 获取消息，设置1秒超时
                msg = wcf.get_msg()
                if msg:
                    logger.debug("收到新消息，开始处理")
                    handle_message(wcf, msg, config)  # 将配置传递给handle_message
            except Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                logger.error(f"获取消息时发生错误: {e}", exc_info=True)
                
            # 检查消息接收状态
            if not wcf.is_receiving_msg():
                logger.error("消息接收功能已断开")
                break
            
            # 短暂休眠，避免CPU占用过高
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在停止骰子机器人...")
    except Exception as e:
        logger.error(f"运行时发生错误: {e}", exc_info=True)
    finally:
        logger.debug("开始清理资源")
        wcf.cleanup()
        logger.debug("已清理 WCF 资源")
        logger.info("骰子机器人已停止")

if __name__ == "__main__":
    main()