import re
import random
import logging
from typing import Tuple, List, Union
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
    handlers=[
        logging.FileHandler('robot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@dataclass
class DiceRoll:
    """骰子投掷结果"""
    num_dice: int
    faces: int
    modifier: int
    advantage: str
    adv_dice: int
    result: int
    detailed_rolls: List[List[int]]
    
    def format_expression(self) -> str:
        """格式化骰子表达式"""
        expr = f"{self.num_dice}d{self.faces}" if self.num_dice > 1 else f"d{self.faces}"
        if self.advantage:
            expr += f"{self.advantage}{self.adv_dice}"
        return expr  # 修正值将在详细结果中显示
    
    def format_detailed_result(self) -> str:
        """格式化详细投掷结果"""
        # 检查是否为嵌套表达式或多次投掷
        if self.num_dice > 1:
            # ���套或多次投掷格式
            base_expr = f"d{self.faces}"
            if self.modifier != 0:
                base_expr += f" {'+' if self.modifier > 0 else ''}{self.modifier}"
            expr = f"{self.num_dice}({base_expr})"
        else:
            # 单次投掷格式
            expr = f"d{self.faces}"
            if self.modifier != 0:
                expr += f" {'+' if self.modifier > 0 else ''}{self.modifier}"
        
        # 详细结果
        if self.advantage:
            # 优势/劣势投掷的详细结果
            roll_details = []
            for rolls in self.detailed_rolls:
                if len(rolls) > 1:
                    chosen = max(rolls) if self.advantage == 'a' else min(rolls)
                    roll_str = f"({' '.join(map(str, rolls))})"
                    roll_details.append(f"{roll_str}={chosen}")
                else:
                    roll_details.append(str(rolls[0]))
            
            result = f"{expr}[ {' | '.join(roll_details)} ]"
        else:
            # 普通或嵌套投掷的详细结果
            roll_str = ' | '.join(str(rolls[0]) for rolls in self.detailed_rolls)
            result = f"{expr}[ {roll_str} ]"
        
        # 添加调整值和最终结果
        if self.modifier != 0:
            result += f" {'+' if self.modifier > 0 else ''}{self.modifier}"
        
        # 始终添加等号和结果
        result += f" = {self.result}"
        
        return result

def parse_nested_expression(expr: str) -> Tuple[List[Tuple[int, int, int, str, int]], Union[None, str]]:
    """解析嵌套的骰子表达式"""
    # 处理嵌套格式：数字(表达式)
    nested_pattern = r'^(\d+)\((\d*d\d+([ap]\d+)?([+-]\d+)?)\)$'
    nested_match = re.match(nested_pattern, expr)
    
    if nested_match:
        repeat_times, inner_expr = nested_match.groups()[:2]
        repeat_times = int(repeat_times)
        
        # 解析内部表达式
        inner_params, invalid = parse_roll_expression(inner_expr)
        if invalid:
            return [], expr
            
        # 重复内部表达式的参数
        repeated_params = []
        for _ in range(repeat_times):
            repeated_params.extend(inner_params)
            
        return repeated_params, None
        
    return [], expr

def parse_roll_expression(expr: str) -> Tuple[List[Tuple[int, int, int, str, int]], Union[None, str]]:
    """解析骰子表达式组合"""
    dice_params = []
    expressions = expr.strip().split()
    invalid_text = []
    
    logger.debug(f"解析表达式: {expressions}")
    
    for single_expr in expressions:
        logger.debug(f"处理单个表达式: {single_expr}")
        
        # 首先尝试解析嵌套表达式
        nested_params, nested_invalid = parse_nested_expression(single_expr)
        if nested_params:
            dice_params.extend(nested_params)
            continue
            
        # 如果不是嵌套表达式，按普通表达式处理
        # 默认值
        num_dice = 1
        num_faces = 100  # 默认100面骰
        modifier = 0
        advantage = ''
        adv_dice = 0
        
        # 使用正则表达式解析
        # 格式: [次数]d[面数][优势类型][优势骰子数][+-调整值]
        pattern = r'^(\d+)?d(\d+)([ap])?(\d+)?([+-]\d+)?$'
        match = re.match(pattern, single_expr)
        
        if match:
            # 解析各个部分
            dice_num, faces, adv, adv_num, mod = match.groups()
            logger.debug(f"匹配结果: dice_num={dice_num}, faces={faces}, adv={adv}, adv_num={adv_num}, mod={mod}")
            
            if dice_num:
                num_dice = int(dice_num)
            if faces:
                num_faces = int(faces)
            if adv:
                advantage = adv
                if adv_num:
                    adv_dice = int(adv_num)
                else:
                    adv_dice = 2  # 默认2个优势/劣势
            if mod:
                modifier = int(mod)
                
            dice_params.append((num_dice, num_faces, modifier, advantage, adv_dice))
        else:
            # 收集无法解析的文本
            logger.debug(f"无法解析表达式: {single_expr}")
            invalid_text.append(single_expr)
            
    return dice_params, " ".join(invalid_text) if invalid_text else None

def roll_single_dice(num_rolls: int, faces: int, modifier: int, advantage: str, adv_dice: int) -> DiceRoll:
    """投掷骰子并计算结果
    
    Args:
        num_rolls: 投掷次数
        faces: 骰子面数
        modifier: 调整值
        advantage: 优势类型 ('a'/'p')
        adv_dice: 优势/劣势骰子数
    """
    all_results = []
    
    for _ in range(num_rolls):
        if advantage and adv_dice > 0:
            # 优势/劣势投掷：同时投掷多个骰子
            current_rolls = [random.randint(1, faces) for _ in range(adv_dice)]
            all_results.append(current_rolls)
        else:
            # 普通投掷
            rolls = [random.randint(1, faces)]
            all_results.append(rolls)
    
    # 计算最终结果
    final_results = []
    for rolls in all_results:
        if advantage == 'a':
            # 优势：取最大值
            final_results.append(max(rolls))
        elif advantage == 'p':
            # 劣势：取最小值
            final_results.append(min(rolls))
        else:
            # 普通：只有一个值
            final_results.append(rolls[0])
    
    # 总和加上调整值
    final_result = sum(final_results) + modifier
    
    return DiceRoll(
        num_dice=num_rolls,  # 现在表示投掷次数
        faces=faces,
        modifier=modifier,
        advantage=advantage,
        adv_dice=adv_dice,  # 现在表示优势/劣势骰子数
        result=final_result,
        detailed_rolls=all_results
    )

def dicehelp() -> str:
    """返回帮助信息"""
    help_text = """骰子指令说明:
格式: .r [投掷次数]d[面数][优势类型][优势骰子数][+-调整值]
      .r 重复次数(表达式)

基础示例:
.r d100       - 投掷1次d100
.r 2d6+3      - 投掷2次d6并+3
.r 4d6-2      - 投掷4次d6并-2

优势/劣势:
.r d20a3      - 投掷1次d20(同时投3个骰子取最大值)
.r d20p3      - 投掷1次d20(同时投3个骰子取最小值)

嵌套表达式:
.r 3(d4+2)    - 投掷3次(1d4+2)
.r 2(d20a2)   - 投掷2次(1d20优势2)

复杂组合:
.r 2d20+3 d8  - 投掷2次d20+3和1次d8
.r d20a3+5 2d6-1 d8  - 投掷1次3优势d20+5, 2次d6-1和1次d8
.r 4d6+2 d20p2-1 3d4  - 投掷4次d6+2, 1次2劣势d20-1和3次d4
.r 3(d6+2) 2(d20a2)   - 投掷3次(d6+2)和2次(d20优势2)

说明:
1. d前的数字表示投掷次数
2. a/p后的数字表示同时投掷的骰子数
   - a表示优势，取最大值
   - p表示劣势，取最小值
3. 优劣势骰子数量最多为3
4. 可以组合多个骰子表达式，用空格分隔
5. 可以使用数字(表达式)的形式重复相同的表达式
6. 每个表达式都可以包含投掷次数、面数、优势/劣势和调整值
7. 默认使用1d100"""
    return help_text

def process_roll_command(command: str) -> Tuple[List[DiceRoll], Union[int, str]]:
    """处理骰子命令并返回结果"""
    dice_params, invalid_expr = parse_roll_expression(command)
    
    # 如果没有有效的骰子表达式
    if not dice_params:
        help_text = dicehelp()
        return [], f"无效的骰子表达式: {invalid_expr}\n{help_text}"
    
    # 处理有效的骰子表达式
    roll_results = [roll_single_dice(*params) for params in dice_params]
    total_result = sum(roll.result for roll in roll_results)
    
    # 如果有无效文本，添加到结果中
    if invalid_expr:
        return roll_results, (total_result, invalid_expr)
    
    return roll_results, total_result

def format_reply_message(nickname: str, roll_results: List[DiceRoll], result: Union[int, Tuple[int, str]]) -> str:
    """格式化回复消息"""
    reply = f"【{nickname}】\n"
    
    if isinstance(result, str):
        # 处理无效的骰子表达式
        reply += result
    elif isinstance(result, tuple):
        # 骰子结果 + 额外文本
        total, text = result
        results = [roll.format_detailed_result() for roll in roll_results]
        reply += "\n".join(results)  # 每个结果单独一行
        if len(roll_results) > 1:
            reply += f"\n= {total}"
        reply += f"\n{text}"
    else:
        # 普通骰子结果
        results = [roll.format_detailed_result() for roll in roll_results]
        reply += "\n".join(results)  # 每个结果单独一行
        if len(roll_results) > 1:
            reply += f"\n= {result}"
    
    return reply