import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from database import db
import json
import os
import random

logger = logging.getLogger(__name__)

@dataclass
class CharacterCard:
    """角色卡数据结构"""
    basic: Dict[str, Any]      # 基础信息
    attributes: Dict[str, Any]  # 属性值
    skills: Dict[str, Any]     # 技能值
    status: Dict[str, Any]     # 状态信息
    items: list               # 物品列表
    notes: list               # 笔记列表
    weapons: list            # 武器列表
    combat: Dict[str, Any]   # 战斗信息
    custom_skills: list      # 自定义技能
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CharacterCard':
        """从字典创建角色卡实例"""
        return cls(
            basic=data.get('basic', {}),
            attributes=data.get('attributes', {}),
            skills=data.get('skills', {}),
            status=data.get('status', {}),
            items=data.get('items', []),
            notes=data.get('notes', []),
            weapons=data.get('weapons', []),
            combat=data.get('combat', {}),
            custom_skills=data.get('customSkills', [])
        )

class CharacterManager:
    """角色卡管理器"""
    
    def __init__(self):
        """初始化角色卡管理器"""
        self.db = db  # 添加数据库实例
    
    def validate_character_data(self, data: dict) -> bool:
        """验证角色卡数据格式"""
        try:
            # 检查必需字段
            required_fields = ['basic', 'attributes', 'skills', 'status']
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                logger.debug(f"缺少必需字段: {missing_fields}")
                return False
                
            # 检查基础信息
            basic = data.get('basic', {})
            if not isinstance(basic, dict):
                logger.debug("basic 不是字典类型")
                return False
            
            basic_required = ['characterName', 'playerName', 'occupation']
            missing_basic = [f for f in basic_required if f not in basic]
            if missing_basic:
                logger.debug(f"缺少基础信息字段: {missing_basic}")
                return False
            
            # 检查属性值
            attributes = data.get('attributes', {})
            if not isinstance(attributes, dict):
                logger.debug("attributes 不是字典类型")
                return False
            
            # 检查必需的属性
            required_attrs = ['str', 'con', 'siz', 'dex', 'app', 'int', 'pow', 'edu']
            missing_attrs = [attr for attr in required_attrs if attr not in attributes]
            if missing_attrs:
                logger.debug(f"缺少必需属性: {missing_attrs}")
                return False
            
            # 检查状态信息
            status = data.get('status', {})
            if not isinstance(status, dict):
                logger.debug("status 不是字典类型")
                return False
            
            # 检查必需的状态字段
            required_status = ['sanity', 'health', 'magic']
            missing_status = [s for s in required_status if s not in status]
            if missing_status:
                logger.debug(f"缺少必需状态字段: {missing_status}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证角色卡数据时出错: {e}", exc_info=True)
            return False
    
    async def load_character(self, file_content: str, user_id: str, room_id: Optional[str] = None) -> tuple[bool, str]:
        """加载角色卡文件"""
        try:
            # 解析JSON数据
            try:
                data = json.loads(file_content)
            except json.JSONDecodeError as e:
                return False, f"JSON格式错误：{str(e)}"

            # 验证角色卡数据
            if not isinstance(data, dict):
                return False, "无效的角色卡格式：数据必须是JSON对象"

            # 保存到数据库，同时记录历史
            success, message = self.db.save_character(data, user_id, room_id)
            return success, message

        except Exception as e:
            logger.error(f"加载角色卡失败: {e}")
            return False, f"加载角色卡失败：{str(e)}"

    def list_characters(self) -> str:
        """显示所有角色卡列表（包含使用状态）"""
        try:
            # 从数据库获取所有角色卡及其使用状态
            chars = self.db.get_character_with_usage()
            if not chars:
                return "没有找到任何角色卡"
            
            result = ["📜 角色卡列表："]
            for char in chars:
                # 构建使用状态信息
                status = ""
                if char['used_by']:
                    env = "群聊" if char['room_id'] else "私聊"
                    status = f"[被 {char['used_by']} 在{env}中使用]"
                
                # 格式化每个角色卡的信息
                result.append(
                    f"• {char['char_name']} ({char['player_name']}) - "
                    f"{char['occupation']} {status}"
                )
            
            return "\n".join(result)
        except Exception as e:
            logger.error(f"获取角色列表失败: {e}")
            return "获取角色列表失败"

    def show_character_info(self, char_name: str) -> str:
        """显示角色卡信息"""
        try:
            char_data = self.db.get_character_info(char_name)
            if not char_data:
                return f"未找到角色卡: {char_name}"
            
            # 基础信息
            basic = char_data['basic']
            basic_info = [
                "=== 角色卡信息 ===",
                "【基础信息】",
                f"姓名: {basic.get('characterName', '未知')}",
                f"玩家: {basic.get('playerName', '未知')}",
                f"职业: {basic.get('occupation', '未知')}",
                f"年龄: {basic.get('age', '未知')}",
                f"性别: {basic.get('gender', '未知')}",
                f"居住地: {basic.get('residence', '未知')}",
                f"出生地: {basic.get('birthplace', '未知')}"
            ]
            
            # 属性信息
            attr_info = ["", "【属性】"]
            attr_names = {
                'str': '力量', 'con': '体质', 'siz': '体型',
                'dex': '敏捷', 'app': '外貌', 'int': '智力',
                'pow': '意志', 'edu': '教育', 'luc': '幸运'
            }
            # 每行显示3个属性，对齐显示
            attr_values = []
            current_line = []
            for attr_key, attr_name in attr_names.items():
                value = char_data['attributes'].get(attr_key, '未知')
                current_line.append(f"{attr_name}: {value:>3}")  # 右对齐数值
                if len(current_line) == 3:
                    attr_values.append('    '.join(current_line))  # 使用4个空格分隔
                    current_line = []
            if current_line:
                attr_values.append('    '.join(current_line))
            attr_info.extend(attr_values)
            
            # 状态信息
            status = char_data['status']
            status_info = ["", "【状态】"]
            
            # 获取状态值
            san = status.get('sanity', {})
            hp = status.get('health', {})
            mp = status.get('magic', {})
            
            # 格式化状态显示
            status_values = [
                f"理智: {san.get('current', '未知'):>3}/{san.get('max', '未知'):<3}",
                f"生命: {hp.get('current', '未知'):>3}/{hp.get('max', '未知'):<3}",
                f"魔法: {mp.get('current', '未知'):>3}/{mp.get('max', '未知'):<3}"
            ]
            status_info.extend(status_values)
            
            return "\n".join(basic_info + attr_info + status_info)
            
        except Exception as e:
            logger.error(f"显示角色卡信息失败: {e}")
            return "获取角色卡信息失败"
    
    def show_character_history(self, char_name: str) -> str:
        """显示角色卡历史"""
        try:
            # 修改 history_type 为 'basic'，让数据库方法知道只需要基本操作历史
            history = self.db.get_character_history(char_name, history_type='basic')
            if not history:
                return f"未找到角色卡 {char_name} 的历史记录"
            
            result = [f"=== 角色卡操作历史 ===", f"角色: {char_name}", ""]
            
            for created_at, user_id, room_id, action, field_name, old_value, new_value, points_used in history:
                time_str = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
                env = "群聊" if room_id else "私聊"
                
                # 只处理基本操作类型
                if action == "create":
                    result.append(f"[{time_str}] 创建角色")
                    result.append(f"操作者: {user_id}")
                    result.append(f"环境: {env}")
                elif action == "use":
                    result.append(f"[{time_str}] 使用角色")
                    result.append(f"操作者: {user_id}")
                    result.append(f"环境: {env}")
                elif action == "release":
                    result.append(f"[{time_str}] 释放角色")
                    result.append(f"操作者: {user_id}")
                    result.append(f"环境: {env}")
                
                result.append("")  # 添加空行分隔
            
            return "\n".join(result[:-1])  # 移除最后一个空行
            
        except Exception as e:
            logger.error(f"显示角色卡历史失败: {e}")
            return "获取角色卡历史失败"

    def show_growth_history(self, char_name: str) -> str:
        """显示角色成长历史"""
        try:
            # 分别获取成长记录和点数调整记录
            grow_history = self.db.get_character_history(char_name, history_type='grow')
            setgrow_history = self.db.get_character_history(char_name, history_type='setgrow')
            
            if not grow_history and not setgrow_history:
                return f"未找到角色 {char_name} 的成长历史"
            
            # 合并历史记录并按时间排序
            history = sorted(grow_history + setgrow_history, 
                            key=lambda x: x[0],  # 按时间排序
                            reverse=True)  # 倒序
            
            # 获取当前剩余成长次数
            current_points = self.db.get_growth_points(char_name)
            
            result = [
                f"=== 技能成长历史 ===",
                f"角色: {char_name}",
                f"当前剩余成长点数: {current_points}",
                ""
            ]
            
            # 按日期分组统计
            date_groups = {}
            for created_at, user_id, room_id, action, field_name, old_value, new_value, points_used in history:
                date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
                time = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
                
                if date not in date_groups:
                    date_groups[date] = {
                        'records': [],
                        'points_gained': 0,  # 获得的点数
                        'points_used': 0,    # 消耗的点数
                        'setgrow_records': [],  # 专门存储成长点数调整记录
                        'grow_records': []    # 专门存储技能成长记录
                    }
                
                # 计算成长值
                try:
                    growth = int(new_value) - int(old_value)
                except:
                    growth = 0
                
                if action == "grow":
                    points = points_used if points_used is not None else 1
                    date_groups[date]['grow_records'].append({
                        'time': time,
                        'user_id': user_id,
                        'skill': field_name,
                        'old_value': old_value,
                        'new_value': new_value,
                        'growth': growth,
                        'points_used': points
                    })
                    date_groups[date]['points_used'] += points
                elif action == "setgrow":
                    try:
                        old_points = int(old_value or 0)
                        new_points = int(new_value or 0)
                        points_change = new_points - old_points
                    except ValueError:
                        points_change = 0
                    
                    date_groups[date]['setgrow_records'].append({
                        'time': time,
                        'user_id': user_id,
                        'old_value': old_value,
                        'new_value': new_value,
                        'points_change': points_change
                    })
                    if points_change > 0:
                        date_groups[date]['points_gained'] += points_change
            
            # 按日期倒序排序
            for date in sorted(date_groups.keys(), reverse=True):
                result.append(f"【{date}】")
                
                # 先显示点数获得情况
                if date_groups[date]['points_gained'] > 0:
                    result.append(f"获得成长点数: +{date_groups[date]['points_gained']}")
                if date_groups[date]['points_used'] > 0:
                    result.append(f"消耗成长点数: -{date_groups[date]['points_used']}")
                result.append("")  # 空行分隔
                
                # 先显示成长点数调整记录
                for record in sorted(date_groups[date]['setgrow_records'], key=lambda x: x['time'], reverse=True):
                    change_text = "+" + str(record['points_change']) if record['points_change'] > 0 else str(record['points_change'])
                    result.extend([
                        f"[{record['time']}] 成长点数调整",
                        f"操作者: {record['user_id']}",
                        f"变更: {record['old_value']} → {record['new_value']} ({change_text})",
                        ""
                    ])
                
                # 再显示技能成长记录
                for record in sorted(date_groups[date]['grow_records'], key=lambda x: x['time'], reverse=True):
                    result.extend([
                        f"[{record['time']}] {record['skill']}",
                        f"操作者: {record['user_id']}",
                        f"成长: {record['old_value']} → {record['new_value']} (+{record['growth']})",
                        f"消耗点数: {record['points_used']}",
                        ""
                    ])
            
            if len(result) == 4:  # 只有标题和剩余次数
                return f"角色 {char_name} 暂无成长记录"
            
            return "\n".join(result[:-1])  # 移除最后一个空行
            
        except Exception as e:
            logger.error(f"显示成长历史失败: {e}")
            return "获取成长历史失败"

    def use_character(self, user_id: str, room_id: Optional[str], char_name: str) -> tuple[bool, str]:
        """设置用户当前使用的角色"""
        try:
            # 检查角色是否存在
            char_info = self.db.get_character_info(char_name)
            if not char_info:
                return False, f"未找到角色「{char_name}」"
            
            # 使用 use_character
            success, message = self.db.use_character(user_id, room_id, char_name)
            if not success:
                return False, message
            
            return True, f"已切换到角色「{char_name}」"
            
        except Exception as e:
            logger.error(f"使用角色失败: {e}")
            return False, f"使用角色失败: {str(e)}"
    
    def release_character(self, user_id: str, room_id: Optional[str]) -> tuple[bool, str]:
        """释放当前使用的角色"""
        try:
            return self.db.release_character(user_id, room_id)
        except Exception as e:
            logger.error(f"释放角色失败: {e}")
            return False, "释放角色失败，请重试"
    
    def get_current_character(self, user_id: str, room_id: Optional[str]) -> Optional[str]:
        """获取用户当前使用的角色名称"""
        return self.db.get_active_character(user_id, room_id)

    def show_character_status(self) -> str:
        """显示所有角色卡的使用状态"""
        try:
            usage_list = self.db.get_all_character_usage()
            if not usage_list:
                return "当前没有角色卡被使用"
            
            result = ["🎭 角色卡使用状态："]
            for char_name, user_id, room_id, updated_at in usage_list:
                env = "群聊" if room_id else "私聊"
                result.append(f"• 「{char_name}」被 {user_id} 在{env}中使用")
            
            return "\n".join(result)
        except Exception as e:
            logger.error(f"获取角色使用状态失败: {e}")
            return "获取角色使用状态失败"

    async def force_release_character(self, char_name: str) -> tuple[bool, str]:
        """强制释放角色卡（管理员功能）"""
        try:
            return self.db.force_release_character(char_name)
        except Exception as e:
            logger.error(f"强制释放角色失败: {e}")
            return False, "强制释放角色失败"

    def check_skill(self, user_id: str, room_id: Optional[str], skill_name: str) -> tuple[bool, str]:
        """检定技能值"""
        try:
            # 获取当前角色
            char_name = self.db.get_active_character(user_id, room_id)
            if not char_name:
                return False, "请先使用 .char use <角色名> 选择要使用的角色"
            
            # 获取技能值和角色信息
            skills_data, error = self.db.get_character_skills(char_name)
            char_info = self.db.get_character_info(char_name)
            
            if not skills_data or not char_info:
                return False, error or f"获取角色「{char_name}」的数据失败"
            
            logger.debug(f"正在为角色「{char_name}」检定技能「{skill_name}」")
            
            # 基本属性映射
            attr_names = {
                '力量': 'str', '体质': 'con', '体型': 'siz',
                '敏捷': 'dex', '外貌': 'app', '智力': 'int',
                '意志': 'pow', '教育': 'edu', '幸运': 'luc'
            }
            
            # 检查是否是基本属性检定
            if skill_name in attr_names:
                attr_key = attr_names[skill_name]
                skill_value = int(char_info['attributes'].get(attr_key, '0') or '0')
                logger.debug(f"找到属性值: {skill_name} = {skill_value}")
            else:
                skill_value = None
                
                # 在普通技能中查找
                for skill in skills_data.get('skillsList', []):
                    if not skill.get('isSubSkill'):
                        skill_name_found = skill['name']
                        
                        # 只在找到匹配的技能时输出日志
                        if skill_name_found == skill_name:
                            skill_value = self._calculate_skill_value(skill)
                            logger.debug(f"找到主技能: {skill_name} = {skill_value}")
                            break
                        # 检查子技能
                        elif skill.get('subtype'):  # 如果有子类型
                            if skill.get('subtype') == skill_name:  # 如果用户输入"斗殴"
                                skill_value = self._calculate_skill_value(skill)
                                logger.debug(f"找到子技能: {skill_name} = {skill_value} (父技能: {skill_name_found})")
                                break
                            elif f"{skill_name_found}:{skill.get('subtype')}" == skill_name:  # 如果用户输入"格斗:斗殴"
                                skill_value = self._calculate_skill_value(skill)
                                logger.debug(f"找到完整技能名: {skill_name} = {skill_value}")
                                break
                
                # 如果普通技能中没找到，在自定义技能中查找
                if skill_value is None:
                    for skill in skills_data.get('customSkills', []):
                        if skill['name'] == skill_name:
                            skill_value = self._calculate_skill_value(skill)
                            logger.debug(f"找到自定义技能: {skill_name} = {skill_value}")
                            break
            
            if skill_value is None:
                logger.debug(f"未找到技能「{skill_name}」")
                return False, f"未找到属性或技能「{skill_name}」"
            
            # 进行技能检定
            roll = random.randint(1, 100)
            result = self._judge_roll(roll, skill_value)
            
            # 构造返回消息
            check_type = "属性" if skill_name in attr_names else "技能"
            message = (
                f"角色「{char_name}」进行{skill_name}{check_type}检定：\n"
                f"D100 = {roll}/{skill_value} {result}"
            )
            
            return True, message
            
        except Exception as e:
            logger.error(f"技能检定失败: {e}")
            return False, f"技能检定失败: {str(e)}"

    def _judge_roll(self, roll: int, target: int) -> str:
        """判定骰子结果"""
        if roll == 1:
            return "大成功！"
        elif roll == 100:
            return "大失败！"
        elif roll <= target / 5:
            return "极难成功"
        elif roll <= target / 2:
            return "困难成功"
        elif roll <= target:
            return "成功"
        else:
            return "失败"

    def _calculate_skill_value(self, skill: dict) -> int:
        """计算技能值"""
        base = int(skill.get('base', '0') or '0')
        occupation = int(skill.get('occupation', '0') or '0')
        interest = int(skill.get('interest', '0') or '0')
        growth = int(skill.get('growth', '0') or '0')
        return base + occupation + interest + growth

    def grow_skill(self, user_id: str, room_id: Optional[str], skill_name: str) -> tuple[bool, str]:
        """进行技能成长检定"""
        try:
            # 获取当前角色
            char_name = self.db.get_active_character(user_id, room_id)
            if not char_name:
                return False, "请先使用 .char use <角色名> 选择要使用的角色"
            
            # 解析技能名和成长次数
            parts = skill_name.split()
            if len(parts) > 1:
                try:
                    grow_times = int(parts[-1])
                    skill_name = ' '.join(parts[:-1])
                except ValueError:
                    grow_times = 1
                    skill_name = ' '.join(parts)
            else:
                grow_times = 1
                skill_name = parts[0]
            
            # 获取技能当前值
            skills_data, error = self.db.get_character_skills(char_name)
            if not skills_data:
                return False, error or f"获取角色「{char_name}」的技能数据失败"
            
            # 查找技能
            current_value = 0
            skill_found = False
            
            # 在普通技能中查找
            for skill in skills_data.get('skillsList', []):
                if not skill.get('isSubSkill'):
                    if skill['name'].lower() == skill_name.lower() or \
                       (skill.get('subtype') and f"{skill['name']}:{skill.get('subtype')}".lower() == skill_name.lower()):
                        current_value = self._calculate_skill_value(skill)
                        skill_found = True
                        break
            
            # 在自定义技能中查找
            if not skill_found:
                for skill in skills_data.get('customSkills', []):
                    if skill['name'].lower() == skill_name.lower():
                        current_value = self._calculate_skill_value(skill)
                        skill_found = True
                        break
            
            if not skill_found:
                return False, f"未找到技能「{skill_name}」"
            
            # 找到技能后，再检查成长次数
            available_points = self.db.get_growth_points(char_name)
            if available_points < grow_times:
                return False, f"成长次数不足，当前剩余: {available_points}"
            
            # 记录所有成长结果
            results = []
            total_growth = 0
            original_value = current_value
            points_used = grow_times  # 记录实际消耗的点数
            
            # 进行多次成长检定
            for i in range(grow_times):
                # 使用一点成长次数
                success, message = self.db.use_growth_point(char_name)
                if not success:
                    if i > 0:
                        break  # 已经完成了部分成长
                    return False, message
                
                # 进行成长检定
                check_roll = random.randint(1, 100)
                
                # 判断是否可以成长
                can_grow = False
                if current_value > 95:
                    can_grow = check_roll >= 96
                else:
                    can_grow = check_roll > current_value
                
                if not can_grow:
                    results.append(f"第 {i+1} 次: D100={check_roll} ≤ {current_value} 失败")
                    continue
                
                # 确定成长骰子
                if current_value <= 29:
                    dice = "1d10"
                    sides = 10
                elif current_value <= 49:
                    dice = "1d8"
                    sides = 8
                elif current_value <= 69:
                    dice = "1d6"
                    sides = 6
                elif current_value <= 89:
                    dice = "1d4"
                    sides = 4
                else:
                    dice = "1d3"
                    sides = 3
                
                # 投掷成长值
                if check_roll == 100:  # 大成功，投两次
                    roll1 = random.randint(1, sides)
                    roll2 = random.randint(1, sides)
                    growth = roll1 + roll2
                    growth_detail = f"{dice}+{dice}=[{roll1}+{roll2}]"
                else:
                    growth = random.randint(1, sides)
                    growth_detail = f"{dice}=[{growth}]"
                
                total_growth += growth
                current_value += growth
                results.append(f"第 {i+1} 次: D100={check_roll} > {current_value-growth} 成功, {growth_detail}")
            
            if total_growth > 0:
                # 更新技能成长值
                success = self.db.update_skill_growth(char_name, skill_name, total_growth)
                if not success:
                    return False, "更新技能成长值失败"
                
                # 记录成长历史
                self.db.add_character_history(
                    char_name, 
                    user_id,
                    room_id,
                    "grow",
                    skill_name,  # 技能名
                    str(original_value),  # 原始值
                    str(current_value),   # 新值
                    points_used  # 消耗的点数
                )
            
            # 构建返回消息
            result_msg = [
                f"技能「{skill_name}」({original_value}) 进行 {grow_times} 次成长检定:",
                *results
            ]
            
            if total_growth > 0:
                result_msg.extend([
                    f"总成长值: {total_growth}",
                    f"最终技能值: {current_value}"
                ])
            else:
                result_msg.append("未获得任何成长")
            
            return True, "\n".join(result_msg)
            
        except Exception as e:
            logger.error(f"技能成长失败: {e}")
            return False, f"技能成长失败: {str(e)}"

    def get_help_message(self) -> str:
        """获取帮助信息"""
        return """角色卡命令说明：
.char help - 显示本帮助信息
.char load - 上传角色卡文件
.char list - 显示所有可用角色卡
.char info [角色名] - 显示角色卡信息
.char use <角色名> - 使用指定角色（同时只能使用一个角色）
.char release - 释放当前使用的角色
.char history [角色名] - 显示角色卡操作历史

注意：
1. 同一时间只能使用一个角色
2. 使用新角色前需要先释放当前角色
3. 方括号[]内的参数可选，尖括号<>内的参数必填
4. 角色名如果包含空格，需要用引号括起来"""

    def show_character_list(self, user_id: str, room_id: Optional[str]) -> str:
        """显示角色列表"""
        try:
            characters = self.db.get_character_list()
            if not characters:
                return "当前没有任何角色卡"
            
            # 获取当前用户使用的角色
            current_char = self.db.get_current_character(user_id, room_id)
            
            msg_lines = ["可用角色列表："]
            for char in characters:
                # 标记当前使用的角色
                if current_char and current_char[0] == char[0]:
                    msg_lines.append(f"* {char[1]} (当前使用中)")
                # 标记被其他用户使用的角色
                elif char[2] is not None:
                    msg_lines.append(f"- {char[1]} (已被使用)")
                else:
                    msg_lines.append(f"- {char[1]}")
                
            return "\n".join(msg_lines)
            
        except Exception as e:
            logger.error(f"获取角色列表失败: {e}")
            return "获取角色列表失败，请重试"

# 创建全局角色卡管理器实例
character_manager = CharacterManager() 