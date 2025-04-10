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

            # 检查是否有角色名
            char_name = data.get('basic', {}).get('characterName')
            if not char_name:
                return False, "无效的角色卡格式：缺少角色名称"
            
            # 检查是否存在该角色
            existing_char = self.db.get_character_info(char_name)
            action = "overwrite" if existing_char else "create"

            # 保存到数据库
            success, message = self.db.save_character(data, user_id)
            
            # 记录操作历史
            if success:
                self.record_operation(char_name, user_id, action)
            
            return success, message

        except Exception as e:
            logger.error(f"加载角色卡失败: {e}")
            return False, f"加载角色卡失败：{str(e)}"

    def list_characters(self) -> str:
        """显示所有可用的角色列表"""
        try:
            char_list = self.db.get_all_characters()
            
            if not char_list:
                return "当前没有可用的角色卡"
            
            result = ["📋 可用角色卡列表："]
            
            for char_name, player_name, occupation in char_list:
                # 检查角色是否被使用中
                is_used = False
                user_id = None
                
                try:
                    usage_info = self.db.get_character_usage_info(char_name)
                    if usage_info:
                        is_used = True
                        user_id = usage_info[0]
                except:
                    pass
                
                # 添加角色信息
                char_info = f"👤 {char_name}"
                if player_name:
                    char_info += f" (PL: {player_name})"
                if occupation:
                    char_info += f" - {occupation}"
                
                # 添加使用状态
                if is_used:
                    char_info += f" [🔒 被 {user_id} 使用中]"
                
                result.append(char_info)
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"获取角色列表失败: {e}")
            return "获取角色列表失败"

    def show_character_info(self, char_name: str) -> str:
        """显示角色卡信息"""
        try:
            # 获取角色基本信息
            char_info = self.db.get_character_info(char_name)
            if not char_info:
                return f"未找到角色：{char_name}"
            
            basic = char_info['basic']
            attrs = char_info['attributes']
            
            # 获取技能数据
            skills, error = self.db.get_character_skills(char_name)
            if error:
                logger.warning(f"获取技能数据时出现问题: {error}")
            
            # 获取剩余成长点数
            growth_points = self.db.get_growth_points(char_name)
            
            # 构建显示信息
            result = [f"🎭 角色卡：{char_name}"]
            
            # 基本信息（更紧凑显示）
            result.append("\n📝 基本信息：")
            basic_info_parts = []
            if basic.get('playerName'):
                basic_info_parts.append(f"👤 玩家: {basic['playerName']}")
            if basic.get('occupation'):
                basic_info_parts.append(f"💼 职业: {basic['occupation']}")
            if basic.get('age'):
                basic_info_parts.append(f"🗓️ 年龄: {basic['age']}")
            if basic.get('gender'):
                basic_info_parts.append(f"⚧️ 性别: {basic['gender']}")
            
            # 第一行基本信息
            if basic_info_parts:
                result.append(" | ".join(basic_info_parts))
            
            # 第二行基本信息
            location_info_parts = []
            if basic.get('residence'):
                location_info_parts.append(f"🏠 居住地: {basic['residence']}")
            if basic.get('birthplace'):
                location_info_parts.append(f"🏞️ 出生地: {basic['birthplace']}")
            if basic.get('era'):
                location_info_parts.append(f"📅 时代: {basic['era']}")
            
            if location_info_parts:
                result.append(" | ".join(location_info_parts))
            
            # 属性值
            result.append("\n💪 属性值：")
            result.append(f"力量(STR): {attrs.get('str', '?')} | 体质(CON): {attrs.get('con', '?')} | 体型(SIZ): {attrs.get('siz', '?')}") 
            result.append(f"敏捷(DEX): {attrs.get('dex', '?')} | 外貌(APP): {attrs.get('app', '?')} | 智力(INT): {attrs.get('int', '?')}")
            result.append(f"意志(POW): {attrs.get('pow', '?')} | 教育(EDU): {attrs.get('edu', '?')} | 幸运(LUC): {attrs.get('luc', '?')}")
            
            # 状态值
            result.append("\n❤️ 状态值：")
            
            # 获取status中的当前值、最大值和起始值
            status = char_info.get('status', {})
            
            # 处理生命值
            health_current = status.get('health', {}).get('current', '?')
            health_max = status.get('health', {}).get('max', '?')
            health_temp = status.get('health', {}).get('temp', '')
            
            # 处理魔法值
            magic_current = status.get('magic', {}).get('current', '?')
            magic_max = status.get('magic', {}).get('max', '?')
            magic_temp = status.get('magic', {}).get('temp', '')
            
            # 处理理智值
            sanity_current = status.get('sanity', {}).get('current', '?')
            sanity_start = status.get('sanity', {}).get('start', '?')
            sanity_max = status.get('sanity', {}).get('max', '?')
            
            # 如果current为空但有其他值，则使用其他值
            if not health_current or health_current == '?':
                health_current = health_max
            if not magic_current or magic_current == '?':
                magic_current = magic_max
            if not sanity_current or sanity_current == '?':
                sanity_current = sanity_start or sanity_max
            
            # 显示状态值
            health_display = f"{health_current}/{health_max}"
            magic_display = f"{magic_current}/{magic_max}"
            sanity_display = f"{sanity_current}/{sanity_max}"
            
            result.append(f"生命值(HP): {health_display} | 魔法值(MP): {magic_display} | 理智值(SAN): {sanity_display}")
            
            # 添加临时生命值和临时魔法值
            temp_values = []
            if health_temp and health_temp != '0':
                temp_values.append(f"临时生命值: {health_temp}")
            if magic_temp and magic_temp != '0':
                temp_values.append(f"临时魔法值: {magic_temp}")
            
            if temp_values:
                result.append(" | ".join(temp_values))
            
            # 添加战斗信息
            if 'combat' in char_info and char_info['combat']:
                combat = char_info['combat']
                combat_info_parts = []
                
                if combat.get('damageBonus'):
                    combat_info_parts.append(f"伤害加值: {combat['damageBonus']}")
                if combat.get('spiritBonus'):
                    combat_info_parts.append(f"精神加值: {combat['spiritBonus']}")
                if combat.get('build'):
                    combat_info_parts.append(f"体型: {combat['build']}")
                if combat.get('armor'):
                    combat_info_parts.append(f"护甲: {combat['armor']}")
                
                if combat_info_parts:
                    result.append(f"\n⚔️ 战斗数据：{' | '.join(combat_info_parts)}")
            
            # 成长点数
            result.append(f"\n📈 剩余成长点数: {growth_points}")
            
            # 技能数量统计
            if skills:
                normal_skills = len(skills.get('skillsList', []))
                custom_skills = len(skills.get('customSkills', []))
                result.append(f"\n🎯 技能数量: {normal_skills + custom_skills} (常规: {normal_skills}, 自定义: {custom_skills})")
                
                # 添加职业、兴趣、成长值非零的技能列表
                special_skills = []
                
                # 处理常规技能
                for skill in skills.get('skillsList', []):
                    skill_name = skill['name']
                    if skill.get('subtype'):
                        skill_name = f"{skill_name}:{skill.get('subtype')}"
                    
                    # 计算总技能值
                    base = int(skill.get('base', '0') or '0')
                    occupation = int(skill.get('occupation', '0') or '0')
                    interest = int(skill.get('interest', '0') or '0')
                    growth = int(skill.get('growth', '0') or '0')
                    total = base + occupation + interest + growth
                    
                    # 添加到相应的列表
                    if occupation > 0 or interest > 0 or growth > 0:
                        special_skills.append(f"{skill_name}: {total}")
                
                # 处理自定义技能
                for skill in skills.get('customSkills', []):
                    skill_name = skill['name']
                    
                    # 计算总技能值
                    base = int(skill.get('base', '0') or '0')
                    occupation = int(skill.get('occupation', '0') or '0')
                    interest = int(skill.get('interest', '0') or '0')
                    growth = int(skill.get('growth', '0') or '0')
                    total = base + occupation + interest + growth
                    
                    # 添加到相应的列表
                    if occupation > 0 or interest > 0 or growth > 0:
                        special_skills.append(f"{skill_name}: {total}")
                
                # 添加到结果列表
                if special_skills:
                    result.append(f"\n🎮 技能列表: {' | '.join(special_skills)}")
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"显示角色卡信息失败: {e}")
            return f"获取角色卡「{char_name}」信息失败"

    def show_character_history(self, char_name: str) -> str:
        """显示角色卡历史"""
        try:
            # 获取操作历史记录
            history_records = self.get_operation_history(char_name)
            if not history_records:
                return f"未找到角色卡 {char_name} 的历史记录"
            
            result = [f"📖 角色卡操作历史", f"👤 角色: {char_name}", ""]
            
            for created_at, user_id, action in history_records:
                try:
                    # 转换时间字符串为datetime对象
                    dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                    # 转换为本地时间（针对UTC存储的情况）
                    local_dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                    time_str = local_dt.strftime('%Y-%m-%d %H:%M')
                    
                    # 处理不同类型的操作
                    action_desc = ""
                    action_icon = "🔄"
                    if action == "create":
                        action_desc = "创建角色"
                        action_icon = "🆕"
                    elif action == "use":
                        action_desc = "使用角色"
                        action_icon = "▶️"
                    elif action == "release":
                        action_desc = "释放角色"
                        action_icon = "⏹️"
                    elif action == "overwrite":
                        action_desc = "覆盖角色"
                        action_icon = "🔄"
                    elif action == "force_release":
                        action_desc = "强制释放角色"
                        action_icon = "⚠️"
                    else:
                        action_desc = action
                    
                    result.append(f"{time_str} {user_id} {action_icon} {action_desc}")
                except Exception as e:
                    logger.error(f"处理历史记录时间出错: {e}", exc_info=True)
                    # 如果时间处理失败，使用原始时间字符串
                    result.append(f"{created_at} {user_id} {action}")
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"显示角色卡历史失败: {e}")
            return "获取角色卡历史失败"

    def show_growth_history(self, char_name: str, limit: int = 20) -> str:
        """
        显示角色成长历史
        
        Args:
            char_name: 角色名称
            limit: 最大显示记录条数，默认20条
        """
        try:
            # 获取成长历史记录，限制数量
            history_records = self.db.get_character_growth_history(char_name, limit=limit)
            if not history_records:
                return f"未找到角色 {char_name} 的成长历史"
            
            # 获取当前剩余成长次数
            current_points = self.db.get_growth_points(char_name)
            
            # 使用数据库函数格式化历史记录并返回
            formatted_history = self.db.format_growth_history(history_records)
            
            # 在开头添加标题和当前剩余次数信息
            header = [
                f"👤 角色: {char_name}",
                f"🎲 当前剩余成长点数: {current_points}",
                f"📊 显示最近 {limit} 条记录",
                ""
            ]
            
            # 组合结果并返回
            return "\n".join(header) + "\n" + formatted_history
            
        except Exception as e:
            logger.error(f"显示角色成长历史失败: {e}", exc_info=True)
            return f"显示角色成长历史失败: {str(e)}"

    def show_character_status(self) -> str:
        """显示所有角色卡的使用状态"""
        try:
            usage_list = self.db.get_all_character_usage()
            if not usage_list:
                return "当前没有角色卡被使用"
            
            result = ["👥 角色卡使用状态："]
            for char_name, user_id, updated_at in usage_list:
                result.append(f"• 「{char_name}」🔒 被 {user_id} 使用中")
            
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

    def check_skill(self, skill_name: str, user_id: str, room_id: Optional[str] = None, advantage_type: Optional[str] = None) -> tuple[bool, str]:
        """检定技能或属性 (room_id参数已弃用，仅为兼容性保留)"""
        # 获取当前使用的角色
        logger.debug(f"检定处理-开始检定，参数: skill_name='{skill_name}', advantage_type={advantage_type}")
        
        char_name = self.get_current_character(user_id, None)
        if not char_name:
            logger.debug(f"检定处理-未找到当前角色")
            return False, "请先使用 .char use <角色名> 选择要使用的角色"
            
        logger.debug(f"检定处理-为角色「{char_name}」检定技能「{skill_name}」，优势类型: {advantage_type}")
        
        # 标准化输入的技能名
        orig_skill_name = skill_name
        skill_name = skill_name.strip().lower()
        logger.debug(f"检定处理-原始技能名: '{orig_skill_name}'，标准化后: '{skill_name}'")
        
        # 检查是否为属性检定
        attribute_mapping = {
            "力量": "str", "str": "str",
            "体质": "con", "con": "con",
            "体型": "siz", "siz": "siz",
            "敏捷": "dex", "dex": "dex",
            "外貌": "app", "app": "app",
            "智力": "int", "int": "int",
            "意志": "pow", "pow": "pow",
            "教育": "edu", "edu": "edu",
            "幸运": "luc", "luck": "luc", "luc": "luc",
            "理智": "san", "san": "san", "sanity": "san",
        }
        
        if skill_name in attribute_mapping:
            logger.debug(f"检测到属性检定: {skill_name} -> {attribute_mapping[skill_name]}")
            # 获取角色信息
            char_info = self.db.get_character_info(char_name)
            if not char_info:
                logger.error(f"获取角色信息失败: {char_name}")
                return False, f"获取角色「{char_name}」的信息失败"
            
            attr_key = attribute_mapping[skill_name]
            attr_value = 0
            
            # 特殊处理理智值，只从status中获取
            if attr_key == "san":
                if not char_info.get('status') or not char_info['status'].get('sanity') or not char_info['status']['sanity'].get('current'):
                    logger.error(f"获取理智值失败: status.sanity.current不存在或为空")
                    return False, f"角色「{char_name}」的理智值未设置"
                
                try:
                    attr_value = int(char_info['status']['sanity']['current'])
                    logger.debug(f"从status中获取理智值: {attr_value}")
                except (ValueError, TypeError):
                    logger.error(f"理智值格式错误: {char_info['status']['sanity']['current']}")
                    return False, f"角色「{char_name}」的理智值格式不正确"
            else:
                # 获取其他属性值
                if not char_info.get('attributes'):
                    logger.error(f"获取属性失败: attributes不存在")
                    return False, f"获取角色「{char_name}」的属性数据失败"
                
                attr_value = int(char_info['attributes'].get(attr_key, 0))
                logger.debug(f"获取到属性值: {attr_key} = {attr_value}")
            
            # 获取玩家名字
            player_name = char_info['basic'].get('playerName', user_id)
            
            # 进行检定，考虑优势/劣势
            if advantage_type == 'advantage' or advantage_type == 'disadvantage':
                # 执行两次骰子，然后根据优势/劣势选择结果
                logger.debug(f"检定处理-使用{advantage_type}检定模式")
                roll1 = random.randint(1, 100)
                roll2 = random.randint(1, 100)
                logger.debug(f"检定处理-投掷两次骰子: roll1={roll1}, roll2={roll2}")
                
                if advantage_type == 'advantage':
                    # 优势：取较小值
                    roll = min(roll1, roll2)
                    logger.debug(f"检定处理-优势检定取较小值: {roll}")
                    marked_roll1 = f"{roll1}*" if roll1 < roll2 else f"{roll1}"
                    marked_roll2 = f"{roll2}*" if roll2 < roll1 else f"{roll2}"
                else:
                    # 劣势：取较大值
                    roll = max(roll1, roll2)
                    logger.debug(f"检定处理-劣势检定取较大值: {roll}")
                    marked_roll1 = f"{roll1}*" if roll1 > roll2 else f"{roll1}"
                    marked_roll2 = f"{roll2}*" if roll2 > roll1 else f"{roll2}"
                
                rolls_display = f"{marked_roll1}，{marked_roll2}"
                logger.debug(f"检定处理-最终骰子显示: '{rolls_display}'")
            else:
                # 普通检定
                roll = random.randint(1, 100)
                logger.debug(f"检定处理-普通检定骰子: {roll}")
                rolls_display = str(roll)
            
            success = roll <= attr_value
            logger.debug(f"属性检定结果: {roll} vs {attr_value}, {'成功' if success else '失败'}")
            
            # 记录检定结果
            self.last_check = {
                'skill': skill_name,
                'value': attr_value,
                'roll': roll,
                'success': success
            }
            
            # 返回检定结果
            result_desc = self._judge_roll(roll, attr_value)
            
            return True, self._format_check_result(
                char_name=char_name,
                player_name=player_name,
                skill_name=skill_name.upper() if skill_name in ["str", "con", "siz", "dex", "app", "int", "pow", "edu", "luc", "san"] else skill_name,
                skill_value=attr_value,
                roll=roll,
                rolls_display=rolls_display,
                result=result_desc
            )
            
        else:
            # 查找技能
            try:
                skills_data, error = self.db.get_character_skills(char_name)
                if not skills_data:
                    return False, error or f"获取角色「{char_name}」的技能数据失败"
                
                # 获取角色信息，用于显示玩家名
                char_info = self.db.get_character_info(char_name)
                player_name = char_info['basic'].get('playerName', user_id) if char_info else user_id
                
                # 在普通技能和自定义技能中查找匹配的技能
                skill_value = 0
                skill_found = False
                skill_display_name = skill_name  # 默认显示用户输入的技能名
                
                # 查找普通技能
                for skill in skills_data.get('skillsList', []):
                    skill_matches = False
                    
                    # 检查技能名是否匹配（包括子技能格式）
                    if skill['name'].lower() == skill_name:
                        skill_matches = True
                        skill_display_name = skill['name']
                    elif skill.get('subtype') and f"{skill['name']}:{skill.get('subtype')}".lower() == skill_name:
                        skill_matches = True
                        skill_display_name = f"{skill['name']}:{skill.get('subtype')}"
                    # 处理特殊情况：斗殴技能名可以是"斗殴"或"格斗:斗殴"
                    elif skill_name == "斗殴" and (skill['name'].lower() == "斗殴" or 
                            (skill['name'].lower() == "格斗" and skill.get('subtype') and skill.get('subtype').lower() == "斗殴")):
                        skill_matches = True
                        skill_display_name = "格斗:斗殴" if skill.get('subtype') else "斗殴"
                    
                    if skill_matches:
                        skill_value = self._calculate_skill_value(skill)
                        skill_found = True
                        break
                
                # 如果在普通技能中未找到，查找自定义技能
                if not skill_found:
                    for skill in skills_data.get('customSkills', []):
                        if skill['name'].lower() == skill_name:
                            skill_value = self._calculate_skill_value(skill)
                            skill_display_name = skill['name']
                            skill_found = True
                            break
                
                if not skill_found:
                    return False, f"未找到技能「{skill_name}」"
                
                # 进行检定，考虑优势/劣势
                if advantage_type == 'advantage' or advantage_type == 'disadvantage':
                    # 执行两次骰子，然后根据优势/劣势选择结果
                    roll1 = random.randint(1, 100)
                    roll2 = random.randint(1, 100)
                    
                    if advantage_type == 'advantage':
                        # 优势：取较小值
                        roll = min(roll1, roll2)
                        marked_roll1 = f"{roll1}*" if roll1 < roll2 else f"{roll1}"
                        marked_roll2 = f"{roll2}*" if roll2 < roll1 else f"{roll2}"
                    else:
                        # 劣势：取较大值
                        roll = max(roll1, roll2)
                        marked_roll1 = f"{roll1}*" if roll1 > roll2 else f"{roll1}"
                        marked_roll2 = f"{roll2}*" if roll2 > roll1 else f"{roll2}"
                    
                    rolls_display = f"{marked_roll1}，{marked_roll2}"
                else:
                    # 普通检定
                    roll = random.randint(1, 100)
                    rolls_display = str(roll)
                
                success = roll <= skill_value
                logger.debug(f"技能检定结果: {roll} vs {skill_value}, {'成功' if success else '失败'}")
                
                # 记录检定结果
                self.last_check = {
                    'skill': skill_display_name,
                    'value': skill_value,
                    'roll': roll,
                    'success': success
                }
                
                # 返回检定结果
                result_desc = self._judge_roll(roll, skill_value)
                
                return True, self._format_check_result(
                    char_name=char_name,
                    player_name=player_name,
                    skill_name=skill_display_name,
                    skill_value=skill_value,
                    roll=roll,
                    rolls_display=rolls_display,
                    result=result_desc
                )
                
            except Exception as e:
                logger.error(f"进行技能检定时出错: {e}")
                return False, f"检定出错: {str(e)}"

    def _format_check_result(self, char_name: str, player_name: str, skill_name: str, skill_value: int, roll: int, result: str, rolls_display: str = None) -> str:
        """格式化检定结果"""
        # 为不同结果选择图标
        icon = "🎲"
        if result == "超级大失败":
            icon = "☠️"
        elif result == "大失败":
            icon = "💥"
        elif result == "失败":
            icon = "❌"
        elif result == "成功":
            icon = "✅"
        elif result == "困难成功":
            icon = "⭐"
        elif result == "极难成功":
            icon = "🌟"
        elif result == "大成功":
            icon = "🌈"
        elif result == "超级大成功":
            icon = "🏆"
            
        # 如果没有提供rolls_display，使用roll
        if rolls_display is None:
            rolls_display = str(roll)
            
        # 格式化输出
        return (
            f"{icon} 技能检定：{skill_name}\n"
            f"👤 角色：{char_name} (PL: {player_name})\n"
            f"📊 技能值：{skill_value}\n"
            f"🎲 掷骰：{rolls_display}\n"
            f"📝 结果：{result}"
        )

    def _judge_roll(self, roll: int, skill_value: int) -> str:
        """根据掷骰结果和技能值判断成功等级"""
        # 1.超级大成功
        if (roll == 1 and roll <= skill_value) or (roll <= skill_value/100 and roll <= 5):
            return "超级大成功"
        
        # 2.大成功
        if ((2 <= roll <= 5) and roll <= skill_value) or (roll <= skill_value/20 and roll <= 25):
            return "大成功"
        
        # 3.极难成功
        if roll <= skill_value/5:
            return "极难成功"
        
        # 4.困难成功
        if roll <= skill_value/2:
            return "困难成功"
        
        # 5.成功
        if roll <= skill_value:
            return "成功"
        
        # 8.超级大失败
        if roll == 100:
            return "超级大失败"
        
        # 7.大失败
        if 96 <= roll <= 99 and roll > skill_value:
            return "大失败"
        
        # 6.失败
        return "失败"

    def _calculate_skill_value(self, skill: dict) -> int:
        """计算技能值"""
        base = int(skill.get('base', '0') or '0')
        occupation = int(skill.get('occupation', '0') or '0')
        interest = int(skill.get('interest', '0') or '0')
        growth = int(skill.get('growth', '0') or '0')
        return base + occupation + interest + growth

    def grow_skill(self, user_id: str, room_id: Optional[str], skill_name: str) -> tuple[bool, str]:
        """进行技能成长检定 (room_id参数已弃用，仅为兼容性保留)"""
        try:
            # 获取当前角色
            char_name = self.db.get_active_character(user_id, None)
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
            full_skill_name = skill_name  # 记录完整的技能名（包括子类型）
            
            # 在普通技能中查找，添加模糊匹配
            for skill in skills_data.get('skillsList', []):
                if not skill.get('isSubSkill'):
                    # 完全匹配
                    if skill['name'].lower() == skill_name.lower():
                        current_value = self._calculate_skill_value(skill)
                        full_skill_name = skill['name']
                        skill_found = True
                        break
                    # 子类型完全匹配
                    elif skill.get('subtype') and f"{skill['name']}:{skill.get('subtype')}".lower() == skill_name.lower():
                        current_value = self._calculate_skill_value(skill)
                        full_skill_name = f"{skill['name']}:{skill.get('subtype')}"
                        skill_found = True
                        break
                    # 子类型部分匹配（如"斗殴"匹配"格斗:斗殴"）
                    elif skill.get('subtype') and skill.get('subtype').lower() == skill_name.lower():
                        current_value = self._calculate_skill_value(skill)
                        full_skill_name = f"{skill['name']}:{skill.get('subtype')}"
                        skill_found = True
                        break
                    # 特殊处理：斗殴
                    elif skill_name.lower() == "斗殴" and (
                        skill['name'].lower() == "斗殴" or 
                        (skill['name'].lower() == "格斗" and skill.get('subtype', '').lower() == "斗殴")
                    ):
                        current_value = self._calculate_skill_value(skill)
                        full_skill_name = "格斗:斗殴" if skill.get('subtype') else "斗殴"
                        skill_found = True
                        break
            
            # 在自定义技能中查找
            if not skill_found:
                for skill in skills_data.get('customSkills', []):
                    if skill['name'].lower() == skill_name.lower():
                        current_value = self._calculate_skill_value(skill)
                        full_skill_name = skill['name']
                        skill_found = True
                        break
            
            if not skill_found:
                return False, f"未找到技能「{skill_name}」"
            
            # 找到技能后，再检查成长次数
            available_points = self.db.get_growth_points(char_name)
            if available_points < grow_times:
                return False, f"成长次数不足，当前剩余: {available_points}"
            
            # 记录所有成长结果
            total_growth = 0
            original_value = current_value
            points_used = grow_times  # 记录实际消耗的点数
            successful_rolls = 0  # 记录成功次数
            
            # 收集骰值信息，供显示和存储
            check_rolls = []  # 收集检定骰值
            growth_rolls = []  # 收集成长骰值
            check_results = []  # 收集每次检定的结果
            current_live_value = current_value  # 实时跟踪技能值变化
            
            # 进行多次成长检定
            for i in range(grow_times):
                # 使用一点成长次数
                success, message = self.db.use_growth_point(char_name)
                if not success:
                    if i > 0:
                        break  # 已经完成了部分成长
                    return False, message
                
                # 进行成长骰
                roll = random.randint(1, 100)
                check_rolls.append(str(roll))  # 记录检定骰值
                
                # 正常情况下，骰值需要大于当前技能值才视为成功
                # 特殊规则：如果技能值大于95，则骰值在96-100时总能成长
                success = roll > current_live_value or (current_live_value > 95 and roll >= 96)
                
                # 根据技能值确定成长骰类型
                if success:
                    growth_value = 0  # 初始化成长值
                    
                    if current_live_value < 30:
                        growth_dice = "1d10"
                        growth_base = random.randint(1, 10)
                    elif current_live_value < 50:
                        growth_dice = "1d8"
                        growth_base = random.randint(1, 8)
                    elif current_live_value < 70:
                        growth_dice = "1d6"
                        growth_base = random.randint(1, 6)
                    elif current_live_value < 90:
                        growth_dice = "1d4"
                        growth_base = random.randint(1, 4)
                    else:
                        growth_dice = "1d3"
                        growth_base = random.randint(1, 3)
                    
                    # 检查是否投出了100，获得双倍成长
                    if roll == 100:
                        # 骰值为100时，对应骰子投两次
                        if current_live_value < 30:
                            second_roll = random.randint(1, 10)
                            growth = growth_base + second_roll
                            growth_rolls.append(f"{growth_dice}={growth_base}+{growth_dice}={second_roll}")
                            roll_desc = f"✅ 大成功({roll}>{current_live_value}) +{growth}点 [{growth_dice}={growth_base}+{growth_dice}={second_roll}]"
                        elif current_live_value < 50:
                            second_roll = random.randint(1, 8)
                            growth = growth_base + second_roll
                            growth_rolls.append(f"{growth_dice}={growth_base}+{growth_dice}={second_roll}")
                            roll_desc = f"✅ 大成功({roll}>{current_live_value}) +{growth}点 [{growth_dice}={growth_base}+{growth_dice}={second_roll}]"
                        elif current_live_value < 70:
                            second_roll = random.randint(1, 6)
                            growth = growth_base + second_roll
                            growth_rolls.append(f"{growth_dice}={growth_base}+{growth_dice}={second_roll}")
                            roll_desc = f"✅ 大成功({roll}>{current_live_value}) +{growth}点 [{growth_dice}={growth_base}+{growth_dice}={second_roll}]"
                        elif current_live_value < 90:
                            second_roll = random.randint(1, 4)
                            growth = growth_base + second_roll
                            growth_rolls.append(f"{growth_dice}={growth_base}+{growth_dice}={second_roll}")
                            roll_desc = f"✅ 大成功({roll}>{current_live_value}) +{growth}点 [{growth_dice}={growth_base}+{growth_dice}={second_roll}]"
                        else:
                            second_roll = random.randint(1, 3)
                            growth = growth_base + second_roll
                            growth_rolls.append(f"{growth_dice}={growth_base}+{growth_dice}={second_roll}")
                            roll_desc = f"✅ 大成功({roll}>{current_live_value}) +{growth}点 [{growth_dice}={growth_base}+{growth_dice}={second_roll}]"
                    # 检查特殊规则：技能值大于95，骰值在96-100时总能成长
                    elif current_live_value > 95 and roll >= 96 and roll <= 99:
                        growth = growth_base
                        growth_rolls.append(f"{growth_dice}={growth_base}")
                        roll_desc = f"✅ 特殊成长({roll}≥96,技能>{95}) +{growth}点 [{growth_dice}={growth_base}]"
                    else:
                        growth = growth_base
                        growth_rolls.append(f"{growth_dice}={growth_base}")
                        roll_desc = f"✅ 成功({roll}>{current_live_value}) +{growth}点 [{growth_dice}={growth_base}]"
                    
                    current_live_value += growth
                    total_growth += growth
                    successful_rolls += 1
                else:
                    growth_rolls.append("")  # 失败时不记录成长骰
                    roll_desc = f"❌ 失败({roll}≤{current_live_value})"
                
                # 记录当前检定结果
                check_results.append(f"  #{i+1}: {roll_desc}")
                
                if current_live_value >= 100:
                    current_live_value = 100  # 技能最大值为100
                    break
            
            # 更新技能成长值
            if total_growth > 0:
                # 格式化骰值信息为字符串
                check_roll_str = ", ".join(check_rolls)
                growth_roll_str = ", ".join([roll for roll in growth_rolls if roll])  # 过滤掉空字符串
                
                # 更新技能成长值
                success = self.db.update_skill_growth(
                    char_name, 
                    full_skill_name, 
                    total_growth, 
                    user_id, 
                    points_used,
                    check_roll_str,
                    growth_roll_str
                )
                
                if not success:
                    return False, "更新技能成长值失败"
            
            # 构建返回消息
            message = [
                f"🎮 技能「{skill_name}」成长检定结果:",
                f"📊 初始值: {original_value}",
                f"🔄 消耗成长点数: {points_used}次",
                f"📋 成功次数: {successful_rolls}/{points_used}",
            ]
            
            # 添加详细结果
            if len(check_results) > 0:
                message.append(f"📝 详细结果:")
                message.extend(check_results)
            
            if total_growth > 0:
                message.append(f"📈 总成长值: +{total_growth}点")
                message.append(f"🏆 最终值: {original_value + total_growth}")
            else:
                message.append(f"📈 总成长值: 0点，未获得成长")
                message.append(f"🏆 最终值: {original_value}")
            
            return True, "\n".join(message)
            
        except Exception as e:
            logger.error(f"技能成长失败: {e}", exc_info=True)
            return False, f"技能成长失败: {str(e)}"

    def get_help_message(self) -> str:
        """获取帮助信息"""
        return """🎭 角色卡命令说明：
📜 .char help - 显示本帮助信息
📥 .char load - 上传角色卡文件
📋 .char list - 显示所有可用角色卡
📊 .char info [角色名] - 显示角色卡信息
👤 .char use <角色名> - 使用指定角色（同时只能使用一个角色）
🔄 .char release - 释放当前使用的角色
📖 .char history [角色名] - 显示角色卡操作历史
⚠️ .char force release <角色名> - 强制释放被占用的角色（管理员）

📝 技能检定命令：
🎯 .c <技能名> - 进行技能检定（需先使用角色）
🌟 .ca <技能名> - 进行优势技能检定（掷两次骰，取较低值）
⚠️ .cp <技能名> - 进行劣势技能检定（掷两次骰，取较高值）

📈 技能成长命令：
🎲 .grow <技能名> [次数] - 进行技能成长检定，可指定次数
📝 .grow history [角色名] [显示条数] - 显示角色成长历史
🔄 .setgrow <角色名> <点数> - 设置角色成长点数（管理员）

🔍 查询命令：
.find <关键词> - 查询当前角色卡中的技能、物品和笔记
• 技能：显示名称和总值
• 物品：显示名称、类型和描述
• 笔记：显示标题和内容

🎲 技能成长规则：
• 成长检定使用D100，需要投出大于当前技能值的结果
• 成长值根据当前技能值决定：
  1-29: 1d10 | 30-49: 1d8 | 50-69: 1d6 | 70-89: 1d4 | 90+: 1d3
• 投出100时获得双倍成长值（投两次骰子取总和）
• 技能值>95时，投出96-100总能成长
• 每次成长检定消耗1点成长点数

⚠️ 注意：
1. 同一时间只能使用一个角色
2. 使用新角色前需要先释放当前角色
3. 方括号[]内的参数可选，尖括号<>内的参数必填
4. 角色名如果包含空格，需要用引号括起来"""

    def show_character_list(self, user_id: str, room_id: Optional[str]) -> str:
        """显示用户可用的角色卡列表 (room_id参数已弃用，仅为兼容性保留)"""
        try:
            # 获取所有角色卡
            chars = self.db.get_character_with_usage()
            if not chars:
                return "没有找到任何角色卡"
                
            # 获取当前角色
            current_char = self.db.get_current_character(user_id, None)
            
            # 按照状态分类角色卡
            current_using = []  # 当前用户正在使用的角色
            available = []      # 可用的角色
            unavailable = []    # 其他用户在使用的角色
            
            for char in chars:
                status = ""
                if char['used_by']:
                    if char['used_by'] == user_id:
                        current_using.append(f"• 「{char['char_name']}」({char['player_name']}) - {char['occupation']}")
                    else:
                        unavailable.append(f"• 「{char['char_name']}」({char['player_name']}) - {char['occupation']} [被 {char['used_by']} 使用]")
                else:
                    available.append(f"• 「{char['char_name']}」({char['player_name']}) - {char['occupation']}")
            
            # 构建结果
            result = ["📜 角色卡列表"]
            
            if current_using:
                result.append("\n🎭 当前正在使用：")
                result.extend(current_using)
                
            if available:
                result.append("\n✅ 可用角色：")
                result.extend(available)
                
            if unavailable:
                result.append("\n❌ 不可用角色：")
                result.extend(unavailable)
                
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"显示角色列表失败: {e}")
            return "获取角色列表失败"

    # 添加来自CharacterHistory的方法
    def add_operation_history(self, char_name: str, user_id: str, action: str) -> None:
        """
        记录角色操作历史
        
        Args:
            char_name (str): 角色名称
            user_id (str): 用户ID
            action (str): 操作类型 (create/use/release/overwrite)
        """
        try:
            self.db.add_operation_history(char_name, user_id, action)
            logger.debug(f"已记录角色操作历史: {char_name}, {user_id}, {action}")
        except Exception as e:
            logger.error(f"记录角色操作历史失败: {e}", exc_info=True)

    def add_growth_history(
        self, 
        char_name: str,
        user_id: str,
        action: str,
        field_name: str,
        old_value: str,
        new_value: str,
        points_used: Optional[int] = None,
        check_roll: Optional[str] = None,
        growth_roll: Optional[str] = None
    ) -> None:
        """
        记录角色成长历史
        
        Args:
            char_name (str): 角色名称
            user_id (str): 用户ID
            action (str): 操作类型 (grow/setgrow)
            field_name (str): 变更的字段名称
            old_value (str): 变更前的值
            new_value (str): 变更后的值
            points_used (Optional[int]): 使用的成长点数
            check_roll (Optional[str]): 检定骰值
            growth_roll (Optional[str]): 成长骰值
        """
        try:
            self.db.add_growth_history(char_name, user_id, action, field_name, old_value, new_value, points_used, check_roll, growth_roll)
            logger.debug(f"已记录角色成长历史: {char_name}, {action}, {field_name}, {old_value} -> {new_value}")
        except Exception as e:
            logger.error(f"记录角色成长历史失败: {e}", exc_info=True)

    def get_operation_history(self, char_name: str, limit: int = 50) -> list:
        """
        查询角色操作历史记录 (.char history命令使用)
        
        Args:
            char_name (str): 角色名称
            limit (int): 最大返回记录数
            
        Returns:
            list: 操作历史记录列表
        """
        try:
            return self.db.get_character_operation_history(char_name, limit)
        except Exception as e:
            logger.error(f"获取角色操作历史失败: {e}", exc_info=True)
            return []

    def get_growth_history(self, char_name: str, limit: int = 50) -> list:
        """
        查询角色成长历史记录 (.grow history命令使用)
        
        Args:
            char_name (str): 角色名称
            limit (int): 最大返回记录数
            
        Returns:
            list: 成长历史记录列表
        """
        try:
            return self.db.get_character_growth_history(char_name, limit)
        except Exception as e:
            logger.error(f"获取角色成长历史失败: {e}", exc_info=True)
            return []
    
    # 添加以下方法，用于在其他方法中统一调用历史记录功能
    def record_operation(self, char_name: str, user_id: str, action: str) -> None:
        """记录角色操作历史的便捷方法"""
        self.add_operation_history(char_name, user_id, action)
    
    def record_growth(
        self, 
        char_name: str, 
        user_id: str, 
        field_name: str, 
        old_value: str, 
        new_value: str, 
        points_used: Optional[int] = None,
        check_roll: Optional[str] = None,
        growth_roll: Optional[str] = None
    ) -> None:
        """
        记录角色成长历史的便捷方法
        
        Args:
            char_name: 角色名
            user_id: 用户ID
            field_name: 成长的字段名 
            old_value: 旧值
            new_value: 新值
            points_used: 使用的成长点数
            check_roll: 检定骰值
            growth_roll: 成长骰值
        """
        self.add_growth_history(
            char_name, 
            user_id, 
            "grow", 
            field_name, 
            old_value, 
            new_value, 
            points_used,
            check_roll,
            growth_roll
        )
    
    def record_growth_points_change(self, char_name: str, user_id: str, old_value: str, new_value: str) -> None:
        """记录成长点数变更的便捷方法"""
        self.add_growth_history(char_name, user_id, "setgrow", "growth_points", old_value, new_value, None)

    def find_item(self, keyword: str, user_id: str) -> str:
        """查询数据库中的技能、道具和笔记
        
        Args:
            keyword (str): 查询关键词
            user_id (str): 用户ID
            
        Returns:
            str: 查询结果
        """
        try:
            # 获取用户当前使用的角色
            current_char = self.get_current_character(user_id, None)
            if not current_char:
                return "请先使用 .char use <角色名> 选择要使用的角色"
            
            cursor = self.db.connection.cursor()
            results = []
            
            # 查询技能
            cursor.execute('''
            SELECT c.char_name, cs.skill_name, cs.base, cs.occupation, cs.interest, cs.growth
            FROM character_skills cs
            JOIN characters c ON cs.character_id = c.id
            WHERE c.char_name = ? AND cs.skill_name LIKE ?
            ORDER BY cs.skill_name
            ''', (current_char, f'%{keyword}%'))
            
            skills = cursor.fetchall()
            if skills:
                results.append("🎯 技能:")
                for char_name, skill_name, base, occupation, interest, growth in skills:
                    # 计算技能总值
                    total = sum(int(x or 0) for x in [base, occupation, interest, growth])
                    results.append(f"  • {skill_name}: {total}")
            
            # 查询物品
            cursor.execute('''
            SELECT c.char_name, ci.item_name, ci.type, ci.description
            FROM character_items ci
            JOIN characters c ON ci.character_id = c.id
            WHERE c.char_name = ? AND (ci.item_name LIKE ? OR ci.description LIKE ?)
            ORDER BY ci.item_name
            ''', (current_char, f'%{keyword}%', f'%{keyword}%'))
            
            items = cursor.fetchall()
            if items:
                results.append("\n🎒 物品:")
                for char_name, item_name, item_type, description in items:
                    item_info = f"  • {item_name}"
                    if item_type:
                        item_info += f" [{item_type}]"
                    if description:
                        item_info += f" - {description}"
                    results.append(item_info)
            
            # 查询笔记
            cursor.execute('''
            SELECT c.char_name, cn.title, cn.content
            FROM character_notes cn
            JOIN characters c ON cn.character_id = c.id
            WHERE c.char_name = ? AND (cn.title LIKE ? OR cn.content LIKE ?)
            ''', (current_char, f'%{keyword}%', f'%{keyword}%'))
            
            notes = cursor.fetchall()
            if notes:
                results.append("\n📝 笔记:")
                for char_name, title, content in notes:
                    results.append(f"  • {title} - {content}")
            
            if not results:
                return f"在角色「{current_char}」中未找到包含关键词「{keyword}」的内容"
            
            return "\n".join(results)
            
        except Exception as e:
            logger.error(f"查询数据库失败: {e}")
            return "查询失败，请稍后重试"

    def get_active_character(self, user_id: str, room_id: Optional[str]) -> Optional[str]:
        """获取用户当前使用的角色名称"""
        try:
            cursor = self.db.connection.cursor()
            
            # 忽略 room_id 参数，仅使用 user_id
            cursor.execute('''
            SELECT c.char_name
            FROM character_usage u
            JOIN characters c ON u.character_id = c.id
            WHERE u.user_id = ?
            ORDER BY u.updated_at DESC
            LIMIT 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            return result[0] if result else None
        
        except Exception as e:
            logger.error(f"获取当前角色失败: {e}")
            return None

    def use_character(self, user_id: str, room_id: Optional[str], char_name: str) -> tuple[bool, str]:
        """设置用户当前使用的角色 (room_id参数已弃用，仅为兼容性保留)"""
        try:
            # 检查角色是否存在
            char_info = self.db.get_character_info(char_name)
            if not char_info:
                return False, f"未找到角色「{char_name}」"
            
            # 使用 use_character
            success, message = self.db.use_character(user_id, char_name)
            if not success:
                return False, message
            
            # 记录操作历史
            self.record_operation(char_name, user_id, "use")
            
            return True, f"已切换到角色「{char_name}」"
            
        except Exception as e:
            logger.error(f"使用角色失败: {e}")
            return False, f"使用角色失败: {str(e)}"
    
    def release_character(self, user_id: str, room_id: Optional[str]) -> tuple[bool, str]:
        """释放当前使用的角色 (room_id参数已弃用，仅为兼容性保留)"""
        try:
            # 获取当前角色
            char_name = self.get_current_character(user_id, None)
            if not char_name:
                return False, "当前未使用任何角色"
            
            # 释放角色
            success, message = self.db.release_character(user_id)
            if not success:
                return False, message
            
            # 记录操作历史
            self.record_operation(char_name, user_id, "release")
            
            return True, message
            
        except Exception as e:
            logger.error(f"释放角色失败: {e}")
            return False, "释放角色失败，请重试"
    
    def get_current_character(self, user_id: str, room_id: Optional[str]) -> Optional[str]:
        """获取用户当前使用的角色名称 (room_id参数已弃用，仅为兼容性保留)"""
        return self.db.get_active_character(user_id, None)

# 创建全局角色卡管理器实例
character_manager = CharacterManager() 