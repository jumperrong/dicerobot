import random
from typing import List, Tuple, Union, Optional
from dataclasses import dataclass
import re

class DiceError(Exception):
    """骰子相关的自定义异常"""
    pass

@dataclass
class DiceRoll:
    """骰子投掷的数据结构"""
    count: int = 1
    sides: int = 6
    advantage: Optional[str] = None  # 'p' for disadvantage, 'a' for advantage
    advantage_count: int = 2
    results: List[int] = None
    
    def __post_init__(self):
        self.results = []
    
    def validate(self):
        """验证骰子参数的合法性"""
        if self.count <= 0:
            raise DiceError("骰子数量必须大于0")
        if self.count > 100:
            raise DiceError("骰子数量不能超过100")
            
        if self.sides <= 0:
            raise DiceError("骰子面数必须大于0")
        if self.sides > 1000:
            raise DiceError("骰子面数不能超过1000")
            
        if self.advantage and self.advantage not in ['p', 'a']:
            raise DiceError("优势标记必须是'p'或'a'")
            
        if self.advantage:
            if self.advantage_count < 2:
                raise DiceError("优势/劣势投掷次数必须至少为2")
            if self.advantage_count > 10:
                raise DiceError("优势/劣势投掷次数不能超过10")
    
    def roll(self) -> Tuple[List[int], str]:
        """执行骰子投掷并返回结果和描述"""
        if self.advantage:
            # 优势/劣势投掷
            all_rolls = []
            for _ in range(self.advantage_count):
                group = [random.randint(1, self.sides) for _ in range(self.count)]
                all_rolls.append(group)
            
            # 计算每组的总和
            group_sums = [sum(group) for group in all_rolls]
            
            # 根据优势/劣势选择结果
            if self.advantage == 'a':  # 优势
                final_sum = max(group_sums)
                chosen_index = group_sums.index(final_sum)
            else:  # 劣势
                final_sum = min(group_sums)
                chosen_index = group_sums.index(final_sum)
            
            # 构建详细信息
            detail = ""
            for i, group in enumerate(all_rolls):
                if i == chosen_index:
                    detail += f"[{', '.join(map(str, group))}]* "
                else:
                    detail += f"[{', '.join(map(str, group))}] "
            
            return [final_sum], detail.strip()
        else:
            # 普通投掷
            rolls = [random.randint(1, self.sides) for _ in range(self.count)]
            return rolls, f"[{', '.join(map(str, rolls))}]"

def parse_dice_expression(expression: str) -> DiceRoll:
    """解析骰子表达式，如 2d8p3"""
    # 如果表达式被括号包围，先移除括号
    if expression.startswith('(') and expression.endswith(')'):
        expression = expression[1:-1]
    
    # 更新正则表达式，支持基本骰子表达式
    pattern = r'^(\d+)?d(\d+)(([ap])(\d+)?)?$'
    match = re.match(pattern, expression.lower())
    
    if not match:
        # 如果不是基本骰子表达式，可能是复合表达式
        if '+' in expression or '-' in expression or '*' in expression or '/' in expression:
            # 让上层函数处理复合表达式
            raise DiceError("复合表达式")
        raise DiceError(f"无效的骰子表达式: {expression}")
    
    try:
        # 解析基本部分
        count = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))
        
        # 解析优势/劣势
        advantage = match.group(4)  # 'a' 或 'p'
        advantage_count = int(match.group(5)) if match.group(5) else 2  # 默认2次
        
        # 创建骰子对象
        dice = DiceRoll(
            count=count,
            sides=sides,
            advantage=advantage,
            advantage_count=advantage_count
        )
        
        # 验证参数
        dice.validate()
        
        return dice
        
    except ValueError as e:
        raise DiceError(f"解析骰子表达式时出错: {str(e)}")

@dataclass
class Expression:
    """表达式数据结构"""
    type: str  # 'dice', 'repeat', 'arithmetic', 'number'
    value: str  # 原始表达式
    parts: List['Expression'] = None  # 子表达式
    operator: Union[str, List[str]] = None  # 运算符 (+, -, *, /, :)

def parse_expression(expression: str) -> Expression:
    """解析表达式，返回表达式树"""
    expression = ''.join(expression.split())  # 移除空白
    
    def _parse_with_depth(expr: str, depth: int = 0) -> Expression:
        if depth > 10:
            raise DiceError("表达式嵌套层数过多")
        
        # 1. 处理括号
        expr = handle_parentheses(expr)
        
        # 2. 处理加减法（最低优先级）
        if not expr.startswith('('):
            parts = split_by_operators(expr, '+-')
            if len(parts) > 1:
                return Expression(
                    type='arithmetic',
                    value=expr,
                    parts=[_parse_with_depth(part) for part in parts],
                    operator=[op for op in expr if op in '+-']
                )
        
        # 3. 处理乘除法
        if '*' in expr or '/' in expr:
            parts = split_by_operators(expr, '*/')
            if len(parts) > 1:
                return Expression(
                    type='arithmetic',
                    value=expr,
                    parts=[_parse_with_depth(part) for part in parts],
                    operator=[op for op in expr if op in '*/']
                )
        
        # 4. 处理重复表达式
        if ':' in expr:
            left, right = split_by_operator(expr, ':')
            return Expression(
                type='repeat',
                value=expr,
                parts=[_parse_with_depth(left), _parse_with_depth(right)],
                operator=':'
            )
        
        # 5. 处理骰子表达式
        if 'd' in expr.lower():
            return Expression(type='dice', value=expr)
        
        # 6. 处理纯数字
        if expr.isdigit():
            return Expression(type='number', value=expr)
        
        raise DiceError(f"无效的表达式: {expr}")
    
    return _parse_with_depth(expression)

@dataclass
class EvaluationStep:
    """表达式求值的每一步"""
    step_type: str  # 'dice', 'repeat', 'arithmetic', 'number'
    expression: str  # 原始表达式
    sub_steps: List['EvaluationStep'] = None  # 子步骤
    results: List[int] = None  # 计算结果
    details: List[str] = None  # 详细信息

def evaluate_expression(expr: Expression) -> Tuple[List[int], List[str], EvaluationStep]:
    """计算表达式的值，返回结果、详细信息和计算步骤"""
    step = EvaluationStep(
        step_type=expr.type,
        expression=expr.value,
        sub_steps=[],
        results=[],
        details=[]
    )
    
    if expr.type == 'dice':
        try:
            dice = parse_dice_expression(expr.value)
            results, detail = dice.roll()
            step.results = results
            step.details = [f"{expr.value}={detail}"]
            return results, step.details, step
        except DiceError as e:
            if str(e) == "复合表达式":
                inner_value = expr.value
                if inner_value.startswith('(') and inner_value.endswith(')'):
                    inner_value = inner_value[1:-1]
                inner_expr = parse_expression(inner_value)
                results, details, sub_step = evaluate_expression(inner_expr)
                step.sub_steps.append(sub_step)
                step.results = results
                step.details = details
                return results, details, step
            raise
    
    elif expr.type == 'repeat':
        # 计算重复次数
        base_results, base_details, base_step = evaluate_expression(expr.parts[0])
        step.sub_steps.append(base_step)
        repeat_count = sum(base_results)
        step.details = [base_details[0]]
        
        total_sum = 0
        for i in range(repeat_count):
            results, roll_details, roll_step = evaluate_expression(expr.parts[1])
            step.sub_steps.append(roll_step)
            result_sum = sum(results)
            total_sum += result_sum
            detail_str = f"投掷 {i + 1}: {roll_details[0]}"
            step.details.append(detail_str)
        
        step.results = [total_sum]
        return step.results, step.details, step
    
    elif expr.type == 'arithmetic':
        # 按运算符优先级处理
        # 1. 先处理乘除法
        if any(op in ['*', '/'] for op in expr.operator):
            # 计算第一个操作数
            first_results, first_details, first_step = evaluate_expression(expr.parts[0])
            step.sub_steps.append(first_step)
            current_sum = sum(first_results)
            step.details.extend(first_details)
            
            # 处理乘除法
            for op, part in zip(expr.operator, expr.parts[1:]):
                part_results, part_details, part_step = evaluate_expression(part)
                step.sub_steps.append(part_step)
                part_sum = sum(part_results)
                
                if op == '*':
                    current_sum *= part_sum
                elif op == '/':
                    if part_sum == 0:
                        raise DiceError("除数不能为0")
                    current_sum //= part_sum
                
                step.details.extend(part_details)
        
        # 2. 再处理加减法
        else:
            first_results, first_details, first_step = evaluate_expression(expr.parts[0])
            step.sub_steps.append(first_step)
            current_sum = sum(first_results)
            step.details.extend(first_details)
            
            for op, part in zip(expr.operator, expr.parts[1:]):
                part_results, part_details, part_step = evaluate_expression(part)
                step.sub_steps.append(part_step)
                part_sum = sum(part_results)
                
                if op == '+':
                    current_sum += part_sum
                else:  # op == '-'
                    current_sum -= part_sum
                
                step.details.extend(part_details)
        
        step.results = [current_sum]
        return step.results, step.details, step
    
    elif expr.type == 'number':
        step.results = [int(expr.value)]
        step.details = [str(expr.value)]
        return step.results, step.details, step
    
    else:
        raise DiceError(f"未知的表达式类型: {expr.type}")

def dicehelp() -> str:
    """返回骰子命令的帮助信息"""
    return """🎲 骰子指令说明:
    
基础指令:
• .r 或 r 开头，如 .rd20、rd6
• 省略骰子数量时默认为1，如 d20 = 1d20

基础表达式:
• NdS     掷N个S面骰，如 2d6
• d20     掷1个20面骰
• 2d8+3   掷2个8面骰并加3

高级表达式:
• 优势投掷:  d20a 或 d20a3 (a后数字为投掷次数，默认2次)
• 劣势投掷:  d20p 或 d20p3 (p后数字为投掷次数，默认2次)
• 重复投掷:  d4:d6 (用d4的结果决定投掷d6的次数)
• 带括号重复: d4:(d8+2) (重复投掷括号内的完整表达式)
• 复合运算:  d8*(d4+2) (支持加减乘除和括号)

示例说明:
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

注意事项:
• 表达式中请勿包含空格
• 运算符优先级: () > d > a/p > : > */ > +-
• 括号内的表达式会作为一个整体计算
• 支持的运算符: + - * / : ( )
• 数值限制: 骰子数量≤100，面数≤1000"""

def format_reply_message(nickname: str, result: str, extra_text: Optional[str] = None) -> str:
    """格式化回复消息
    Args:
        nickname: 用户昵称
        result: 完整的骰子结果字符串
        extra_text: 额外的描述文本
    Returns:
        str: 格式化的回复消息
    """
    try:
        # 如果是错误消息（❌开头）
        if result.startswith('❌'):
            return result
            
        # 构建昵称部分，如果额外文本则添加
        name_part = nickname
        if extra_text:
            name_part = f"{nickname} {extra_text}"
            
        # 正常结果的式化
        return f"🎲 {name_part} 掷骰: \n{result}"
        
    except Exception as e:
        return f"❌ 发生未知错误: {str(e)}"

def process_roll_command(command: str) -> Tuple[List[int], str, Optional[str]]:
    """处理骰子命令并返回响应"""
    # 移除命令前缀和空白字符
    command = command.strip()
    extra_text = None
    
    # 分割命令和额外文本
    parts = command.split(maxsplit=1)
    command = parts[0].lower()
    if len(parts) > 1:
        extra_text = parts[1]
    
    # 处理命令前缀
    if command.startswith('.r') or command.startswith('。r'):
        command = command[2:].strip()
    elif command.startswith('r'):
        command = command[1:].strip()
        
    # 处理帮助命令
    if command in ['help', '帮助', '?']:
        return [], dicehelp(), None
        
    # 默认命令
    if not command:
        command = 'd20'
        
    try:
        # 移除所有空白字符并简化表达式
        command = simplify_expression(command)
        
        # 基本验证
        if not any(c in command for c in ['d', 'D']):
            if command.isdigit():
                command = f"d{command}"
            else:
                raise DiceError("无效的骰子表达式")
        
        command = command.lower()
        
        # 验证表达式合法性
        validate_expression(command)
        
        # 解析表达式
        expr = parse_expression(command)
        results, details, eval_step = evaluate_expression(expr)
        
        # 构建结果字符串
        result_str = f"{command}\n骰值:\n"
        
        # 添加计算步骤
        for i, detail in enumerate(format_evaluation_steps(eval_step), 1):
            result_str += f"  {i}. {detail}\n"
        
        # 添加最终结果
        result_str += f"结果: {sum(results)}"
        
        return results, result_str, extra_text
        
    except DiceError as e:
        return [], f"❌ 错误: {str(e)}", None
    except Exception as e:
        return [], f"❌ 发生未知错误: {str(e)}", None

def simplify_expression(expression: str) -> str:
    """简化骰子表达式，移除不必要的括号和空格"""
    # 移除所有空白字符
    expr = ''.join(expression.split())
    
    # 如果整个表达式被括号包围且内部没有运算符，移除外层括号
    while (expr.startswith('(') and expr.endswith(')') and 
           not any(c in expr[1:-1] for c in '+-*/:')): 
        expr = expr[1:-1]
    
    return expr

def validate_expression(expression: str) -> None:
    """验证表达式的合法性，提供更详细的错误提示"""
    if not expression:
        raise DiceError("表达式不能为空")
    
    # 检查括号匹配
    if expression.count('(') != expression.count(')'):
        raise DiceError("括号不匹配")
    
    # 检查非法字符
    valid_chars = set('0123456789dDaApP+-*/:().')
    invalid_chars = set(expression) - valid_chars
    if invalid_chars:
        raise DiceError(f"表达式包含非法字符: {', '.join(invalid_chars)}")
    
    # 检查运算符使用
    operators = '+-*/:' 
    for i, char in enumerate(expression):
        if char in operators:
            if i == 0 or i == len(expression) - 1:
                raise DiceError(f"运算符 '{char}' 不能出现在表达式开头或结尾")
            if expression[i-1] in operators or expression[i+1] in operators:
                raise DiceError(f"运算符 '{char}' 前后不能是其他运算符")

def handle_parentheses(expr: str) -> str:
    """处理括号表达式，返回处理后的表达式"""
    # 如果表达式被括号包围，检查是否可以移除
    while expr.startswith('(') and expr.endswith(')'):
        # 检查是否真的需要移除括号
        bracket_count = 0
        for i, char in enumerate(expr[1:-1]):
            if char == '(':
                bracket_count += 1
            elif char == ')':
                bracket_count -= 1
            # 如果在括号内找到运算符，且不在其他括号内，则保留外层括号
            elif bracket_count == 0 and char in '+-*/:':
                return expr
        # 没有找到需要保留括号的情况，移除外层括号
        expr = expr[1:-1]
    return expr

def split_by_operator(expr: str, operator: str) -> Tuple[str, str]:
    """按指定运算符分割表达式，处理括号嵌套"""
    bracket_count = 0
    for i, char in enumerate(expr):
        if char == '(':
            bracket_count += 1
        elif char == ')':
            bracket_count -= 1
        elif char == operator and bracket_count == 0:
            return expr[:i], expr[i+1:]
    raise DiceError(f"无法按运算符'{operator}'分割表达式")

def split_by_operators(expr: str, operators: str) -> List[str]:
    """按多个运算符分割表达式，保��运算符顺序"""
    parts = []
    current_part = ''
    bracket_count = 0
    
    for char in expr:
        if char == '(':
            bracket_count += 1
            current_part += char
        elif char == ')':
            bracket_count -= 1
            current_part += char
        elif char in operators and bracket_count == 0:
            if current_part:
                parts.append(current_part)
            current_part = ''
        else:
            current_part += char
    
    if current_part:
        parts.append(current_part)
    
    if not parts:
        raise DiceError("表达式分割后为空")
    
    return parts

def format_evaluation_steps(step: EvaluationStep) -> List[str]:
    """格式化计算步骤为可读的字符串列表"""
    details = []
    
    if step.step_type == 'dice':
        details.extend(step.details)
    
    elif step.step_type == 'repeat':
        details.append(step.details[0])  # d4的结果
        details.extend(step.details[1:])  # 各次投掷的结果
    
    elif step.step_type == 'arithmetic':
        if step.expression.startswith('('):
            # 括号内的表达式
            details.extend(step.details)
        else:
            # 普通算术表达式
            for sub_step in step.sub_steps:
                details.extend(format_evaluation_steps(sub_step))
            # 添加计算过程
            if '*' in step.expression or '/' in step.expression:
                left_value = step.sub_steps[0].results[0]
                right_value = step.sub_steps[1].results[0]
                op = '*' if '*' in step.expression else '/'
                details.append(f"计算: {left_value} {op} {right_value} = {step.results[0]}")
    
    return details

# 测试例
if __name__ == "__main__":
    test_expressions = [
        "2d8p3+2",
        "d8:d4",
        "(2d6+1):(1d4)",
        "2d6*3",      # 新增乘法测试
        "6d6/2",      # 新增：除法测试
        "(2d4+1)*3",  # 新增复合运算测试
    ]
    
    for expr in test_expressions:
        try:
            results, calc = format_roll_results(expr)
            print(f"表达式: {expr}")
            print(f"结果: {results}")
            print(f"算过程: {calc}")
        except DiceError as e:
            print(f"错误 - {expr}: {str(e)}")
        print()
