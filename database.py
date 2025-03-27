import sqlite3
import json
import logging
import os
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from sqlite3 import Connection
from contextlib import contextmanager
import queue
import threading
import time

logger = logging.getLogger(__name__)

# 定义数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'characters.db')

class Database:
    def __init__(self, db_path: str = DB_PATH):
        """初始化数据库连接"""
        self.db_path = db_path
        # 确保数据目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # 使用单一连接
        self.connection = sqlite3.connect(
            self.db_path, 
            check_same_thread=False,
            timeout=20.0  # 增加超时时间
        )
        self._init_db()
    
    def _ensure_db_dir(self) -> str:
        """确保数据库目录存在"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(current_dir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'characters.db')
    
    def _init_db(self):
        """初始化数据库表"""
        cursor = self.connection.cursor()
        
        # 角色基础信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            char_name TEXT NOT NULL UNIQUE,
            player_name TEXT,
            occupation TEXT,
            age TEXT,
            gender TEXT,
            residence TEXT,
            birthplace TEXT,
            era TEXT,                    -- 新增：时代
            is_partner BOOLEAN,          -- 新增：是否为搭档
            growth_points INTEGER DEFAULT 0,  -- 成长点数字段
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # 角色属性表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            str INTEGER,           -- 力量
            con INTEGER,           -- 体质
            siz INTEGER,           -- 体型
            dex INTEGER,           -- 敏捷
            app INTEGER,           -- 外貌
            int INTEGER,           -- 智力
            pow INTEGER,           -- 意志
            edu INTEGER,           -- 教育
            luc INTEGER,           -- 幸运（注意：JSON中是luc而不是luck）
            san INTEGER,           -- 理智
            hp INTEGER,            -- 生命值
            mp INTEGER,            -- 魔法值
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
        ''')

        # 角色技能表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            base INTEGER,          -- 基础值
            occupation INTEGER,     -- 职业加值
            interest INTEGER,       -- 兴趣加值
            growth INTEGER,        -- 成长值
            is_custom BOOLEAN DEFAULT 0,  -- 是否为自定义技能
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 添加更新时间字段
            FOREIGN KEY (character_id) REFERENCES characters(id),
            UNIQUE(character_id, skill_name)
        )
        ''')

        # 角色状态表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            category TEXT NOT NULL,      -- sanity/health/magic
            type TEXT NOT NULL,         -- current/start/max/temp
            value TEXT,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
        ''')

        # 角色物品表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            type TEXT,            -- 物品类型
            description TEXT,     -- 物品描述（note字段）
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
        ''')

        # 角色武器表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_weapons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            weapon_name TEXT NOT NULL,
            damage TEXT,           -- 伤害
            features TEXT,         -- 武器特性
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
        ''')

        # 角色笔记表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
        ''')

        # 角色使用状态表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            room_id TEXT,
            character_id INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
        ''')

        # 检查 character_history 表是否存在
        cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='character_history'
        ''')
        
        if cursor.fetchone():
            # 如果表存在，检查是否有 points_used 字段
            cursor.execute('PRAGMA table_info(character_history)')
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'points_used' not in columns:
                # 添加 points_used 字段
                cursor.execute('''
                ALTER TABLE character_history 
                ADD COLUMN points_used INTEGER
                ''')
                logger.info("已添加 points_used 字段到 character_history 表")
        else:
            # 如果表不存在，创建新表
            cursor.execute('''
            CREATE TABLE character_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                room_id TEXT,
                action TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                points_used INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (character_id) REFERENCES characters(id)
            )
            ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_char_name ON characters(char_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_skills_char ON character_skills(character_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_attrs_char ON character_attributes(character_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_char ON character_status(character_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_char ON character_items(character_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_weapons_char ON character_weapons(character_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_char ON character_notes(character_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_char ON character_history(character_id)')
        
        self.connection.commit()
    
    def _validate_character_data(self, char_data: dict) -> tuple[bool, str]:
        """验证角色卡数据的完整性"""
        try:
            # 检查基本信息
            if 'basic' not in char_data:
                return False, "缺少基本信息"
            
            basic = char_data['basic']
            if not basic.get('characterName'):
                return False, "缺少角色名称"
            
            # 检查属性值
            if 'attributes' in char_data:
                attrs = char_data['attributes']
                required_attrs = ['str', 'con', 'siz', 'dex', 'app', 'int', 'pow', 'edu', 'luc']
                for attr in required_attrs:
                    if attr not in attrs:
                        return False, f"缺少属性值: {attr}"
                    try:
                        int(attrs[attr])
                    except ValueError:
                        return False, f"属性值格式错误: {attr}"
            
            return True, ""
            
        except Exception as e:
            return False, f"数据验证失败: {str(e)}"

    def save_character(self, char_data: dict, user_id: str, room_id: Optional[str] = None) -> tuple[bool, str]:
        """保存角色卡数据"""
        # 首先验证数据
        is_valid, error_msg = self._validate_character_data(char_data)
        if not is_valid:
            return False, error_msg
        
        try:
            cursor = self.connection.cursor()
            
            # 1. 保存基本信息
            basic = char_data.get('basic', {})
            cursor.execute('''
            INSERT OR REPLACE INTO characters (
                char_name, player_name, occupation, age, gender, 
                residence, birthplace, era, is_partner
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                basic.get('characterName'),
                basic.get('playerName'),
                basic.get('occupation'),
                basic.get('age'),
                basic.get('gender'),
                basic.get('residence'),
                basic.get('birthplace'),
                basic.get('era'),
                basic.get('isPartner', False)
            ))
            
            character_id = cursor.lastrowid
            
            # 保存属性值
            if 'attributes' in char_data:
                cursor.execute('DELETE FROM character_attributes WHERE character_id = ?', (character_id,))
                attrs = char_data['attributes']
                cursor.execute('''
                INSERT INTO character_attributes (
                    character_id, str, con, siz, dex, app, int, pow, edu, 
                    luc, san, hp, mp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    character_id,
                    int(attrs.get('str', '0')),
                    int(attrs.get('con', '0')),
                    int(attrs.get('siz', '0')),
                    int(attrs.get('dex', '0')),
                    int(attrs.get('app', '0')),
                    int(attrs.get('int', '0')),
                    int(attrs.get('pow', '0')),
                    int(attrs.get('edu', '0')),
                    int(attrs.get('luc', '0')),
                    int(attrs.get('san', '0')),
                    int(attrs.get('hp', '0')),
                    int(attrs.get('mp', '0'))
                ))
            
            # 2. 保存状态数据
            if 'status' in char_data:
                cursor.execute('DELETE FROM character_status WHERE character_id = ?', (character_id,))
                status = char_data['status']
                for category, values in status.items():  # sanity, health, magic
                    for type_, value in values.items():  # current, start, max, temp
                        cursor.execute('''
                        INSERT INTO character_status (
                            character_id, category, type, value
                        ) VALUES (?, ?, ?, ?)
                        ''', (character_id, category, type_, value))
            
            # 3. 保存技能数据
            if 'skills' in char_data and 'skillsList' in char_data['skills']:
                cursor.execute('DELETE FROM character_skills WHERE character_id = ? AND is_custom = 0', (character_id,))
                for skill in char_data['skills']['skillsList']:
                    if not skill.get('isSubSkill'):
                        skill_name = skill['name']
                        
                        # 如果是格斗技能且有子类型，只保存子技能
                        if skill_name == "格斗" and 'subtype' in skill:
                            sub_skill_name = f"格斗:{skill['subtype']}"  # 使用 "格斗:斗殴" 格式
                            cursor.execute('''
                            INSERT INTO character_skills (
                                character_id, skill_name, base, occupation, 
                                interest, growth, is_custom
                            ) VALUES (?, ?, ?, ?, ?, ?, 0)
                            ''', (
                                character_id,
                                sub_skill_name,
                                skill.get('base', '0'),
                                skill.get('occupation', ''),
                                skill.get('interest', ''),
                                skill.get('growth', '')
                            ))
                        # 对于其他非格斗技能，正常保存
                        elif skill_name != "格斗":  # 不保存格斗主技能
                            cursor.execute('''
                            INSERT INTO character_skills (
                                character_id, skill_name, base, occupation, 
                                interest, growth, is_custom
                            ) VALUES (?, ?, ?, ?, ?, ?, 0)
                            ''', (
                                character_id,
                                skill_name,
                                skill.get('base', '0'),
                                skill.get('occupation', ''),
                                skill.get('interest', ''),
                                skill.get('growth', '')
                            ))
            
            # 4. 保存自定义技能
            if 'customSkills' in char_data:
                cursor.execute('DELETE FROM character_skills WHERE character_id = ? AND is_custom = 1', (character_id,))
                for skill in char_data['customSkills']:
                    cursor.execute('''
                    INSERT INTO character_skills (
                        character_id, skill_name, base, occupation, 
                        interest, growth, is_custom
                    ) VALUES (?, ?, ?, ?, ?, ?, 1)
                    ''', (
                        character_id,
                        skill['name'],
                        skill.get('base', '0'),
                        skill.get('occupation', ''),
                        skill.get('interest', ''),
                        skill.get('growth', '')
                    ))
            
            # 5. 保存物品数据
            if 'items' in char_data:
                cursor.execute('DELETE FROM character_items WHERE character_id = ?', (character_id,))
                for item in char_data['items']:
                    if item.get('name'):
                        cursor.execute('''
                        INSERT INTO character_items (
                            character_id, item_name, type, description
                        ) VALUES (?, ?, ?, ?)
                        ''', (
                            character_id,
                            item['name'],
                            item.get('type', ''),
                            item.get('note', '')
                        ))
            
            # 6. 保存武器数据
            if 'weapons' in char_data:
                cursor.execute('DELETE FROM character_weapons WHERE character_id = ?', (character_id,))
                for weapon in char_data['weapons']:
                    if weapon.get('name'):
                        cursor.execute('''
                        INSERT INTO character_weapons (
                            character_id, weapon_name, damage, features
                        ) VALUES (?, ?, ?, ?)
                        ''', (
                            character_id,
                            weapon['name'],
                            weapon.get('damage', ''),
                            weapon.get('features', '')
                        ))
            
            # 7. 保存笔记数据
            if 'notes' in char_data:
                cursor.execute('DELETE FROM character_notes WHERE character_id = ?', (character_id,))
                for note in char_data['notes']:
                    cursor.execute('''
                    INSERT INTO character_notes (
                        character_id, title, content
                    ) VALUES (?, ?, ?)
                    ''', (
                        character_id,
                        note.get('name', ''),
                        note.get('note', '')
                    ))
            
            self.connection.commit()
            return True, f"角色「{basic.get('characterName')}」保存成功"
            
        except Exception as e:
            logger.error(f"保存角色数据失败: {e}")
            return False, f"保存角色数据失败: {str(e)}"
    
    def get_character(self, char_name: str) -> Optional[dict]:
        """获取角色卡数据"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
            SELECT age, gender, residence, birthplace, str, con, siz, dex, app, int, pow, edu, luc, san, hp, mp, mov, build, db, status, items, notes, weapons, combat, custom_skills
            FROM characters c
            JOIN character_attributes a ON c.id = a.character_id
            JOIN character_status s ON c.id = s.character_id
            JOIN character_items i ON c.id = i.character_id
            JOIN character_notes n ON c.id = n.character_id
            JOIN character_weapons w ON c.id = w.character_id
            WHERE c.char_name = ?
            ''', (char_name,))
            
            result = cursor.fetchone()
            if not result:
                return None
            
            # 构建角色卡数据
            return {
                'age': result[0],
                'gender': result[1],
                'residence': result[2],
                'birthplace': result[3],
                'attributes': {
                    'str': result[4],
                    'con': result[5],
                    'siz': result[6],
                    'dex': result[7],
                    'app': result[8],
                    'int': result[9],
                    'pow': result[10],
                    'edu': result[11],
                    'luc': result[12],
                    'san': result[13],
                    'hp': result[14],
                    'mp': result[15],
                    'mov': result[16],
                    'build': result[17],
                    'db': result[18]
                },
                'status': json.loads(result[19]),
                'items': json.loads(result[20]),
                'notes': json.loads(result[21]),
                'weapons': json.loads(result[22]),
                'combat': json.loads(result[23]),
                'customSkills': json.loads(result[24])
            }
            
        except Exception as e:
            logger.error(f"获取角色卡失败: {e}", exc_info=True)
            return None
    
    def get_all_characters(self) -> list:
        """获取所有角色卡的基本信息列表"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('''
            SELECT char_name, player_name, occupation 
            FROM characters 
            ORDER BY created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取角色卡列表失败: {e}")
            return []
    
    def get_character_info(self, char_name: str) -> Optional[dict]:
        """获取指定角色卡的基本信息"""
        try:
            cursor = self.connection.cursor()
            
            # 获取角色ID和基本信息
            cursor.execute('''
            SELECT c.id, c.char_name, c.player_name, c.occupation, c.age, 
                   c.gender, c.residence, c.birthplace, c.era, c.is_partner
            FROM characters c
            WHERE c.char_name = ?
            ''', (char_name,))
            
            basic_info = cursor.fetchone()
            if not basic_info:
                return None
                
            character_id = basic_info[0]
            
            # 获取属性值
            cursor.execute('''
            SELECT str, con, siz, dex, app, int, pow, edu, luc, san, hp, mp
            FROM character_attributes
            WHERE character_id = ?
            ''', (character_id,))
            
            attrs = cursor.fetchone()
            if not attrs:
                attrs = [0] * 12  # 如果没有属性数据，使用默认值
            
            # 获取状态信息
            cursor.execute('''
            SELECT category, type, value 
            FROM character_status 
            WHERE character_id = ?
            ''', (character_id,))
            status_data = cursor.fetchall()
            
            # 获取物品信息
            cursor.execute('''
            SELECT item_name, type, description 
            FROM character_items 
            WHERE character_id = ?
            ''', (character_id,))
            items_data = cursor.fetchall()
            
            # 获取武器信息
            cursor.execute('''
            SELECT weapon_name, damage, features 
            FROM character_weapons 
            WHERE character_id = ?
            ''', (character_id,))
            weapons_data = cursor.fetchall()
            
            # 构造返回数据
            return {
                'basic': {
                    'characterName': basic_info[1],
                    'playerName': basic_info[2],
                    'occupation': basic_info[3],
                    'age': basic_info[4],
                    'gender': basic_info[5],
                    'residence': basic_info[6],
                    'birthplace': basic_info[7],
                    'era': basic_info[8],
                    'isPartner': basic_info[9]
                },
                'attributes': {
                    'str': str(attrs[0]),
                    'con': str(attrs[1]),
                    'siz': str(attrs[2]),
                    'dex': str(attrs[3]),
                    'app': str(attrs[4]),
                    'int': str(attrs[5]),
                    'pow': str(attrs[6]),
                    'edu': str(attrs[7]),
                    'luc': str(attrs[8]),
                    'san': str(attrs[9]),
                    'hp': str(attrs[10]),
                    'mp': str(attrs[11])
                },
                'status': self._format_status_data(status_data),
                'items': [{
                    'name': item[0],
                    'type': item[1],
                    'note': item[2]
                } for item in items_data],
                'weapons': [{
                    'name': weapon[0],
                    'damage': weapon[1],
                    'features': weapon[2]
                } for weapon in weapons_data if weapon[0]]
            }
            
        except Exception as e:
            logger.error(f"获取角色卡信息失败: {e}")
            return None

    def _format_status_data(self, status_data: List[Tuple[str, str, str]]) -> dict:
        """格式化状态数据"""
        status = {
            'sanity': {'current': '', 'start': '', 'max': ''},
            'health': {'current': '', 'max': '', 'temp': ''},
            'magic': {'current': '', 'max': '', 'temp': ''}
        }
        
        for category, type_, value in status_data:
            if category in status:
                status[category][type_] = value
        
        return status
    
    def get_character_history(self, char_name: str, history_type: str = 'all', limit: int = 50) -> list:
        """获取角色卡的变更历史"""
        try:
            cursor = self.connection.cursor()
            
            if history_type == 'grow':
                # 只获取成长相关的历史（只获取技能成长记录）
                cursor.execute('''
                SELECT h.created_at, h.user_id, h.room_id, h.action, 
                       h.field_name, h.old_value, h.new_value,
                       h.points_used
                FROM character_history h
                JOIN characters c ON h.character_id = c.id
                WHERE c.char_name = ? AND h.action = 'grow'
                ORDER BY h.created_at DESC
                LIMIT ?
                ''', (char_name, limit))
            elif history_type == 'setgrow':
                # 获取成长点数调整记录
                cursor.execute('''
                SELECT h.created_at, h.user_id, h.room_id, h.action, 
                       h.field_name, h.old_value, h.new_value,
                       h.points_used
                FROM character_history h
                JOIN characters c ON h.character_id = c.id
                WHERE c.char_name = ? AND h.action = 'setgrow'
                ORDER BY h.created_at DESC
                LIMIT ?
                ''', (char_name, limit))
            elif history_type == 'basic':
                # 只获取基本操作历史（创建、使用、释放）
                cursor.execute('''
                SELECT h.created_at, h.user_id, h.room_id, h.action, 
                       h.field_name, h.old_value, h.new_value,
                       h.points_used
                FROM character_history h
                JOIN characters c ON h.character_id = c.id
                WHERE c.char_name = ? AND h.action IN ('create', 'use', 'release')
                ORDER BY h.created_at DESC
                LIMIT ?
                ''', (char_name, limit))
            else:
                # 获取所有历史
                cursor.execute('''
                SELECT h.created_at, h.user_id, h.room_id, h.action, 
                       h.field_name, h.old_value, h.new_value,
                       h.points_used
                FROM character_history h
                JOIN characters c ON h.character_id = c.id
                WHERE c.char_name = ?
                ORDER BY h.created_at DESC
                LIMIT ?
                ''', (char_name, limit))
            
            return cursor.fetchall()
            
        except Exception as e:
            logger.error(f"获取角色卡历史失败: {e}")
            return []
    
    def use_character(self, user_id: str, room_id: Optional[str], char_name: str) -> tuple[bool, str]:
        """使用角色"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('BEGIN')
            
            # 1. 检查角色是否存在
            cursor.execute('SELECT id, char_name FROM characters WHERE char_name = ?', (char_name,))
            char_result = cursor.fetchone()
            if not char_result:
                self.connection.rollback()
                return False, f"未找到角色「{char_name}」"
            
            character_id, char_name = char_result
            
            # 2. 检查角色是否已被使用
            cursor.execute('''
                SELECT c.char_name, u.user_id 
                FROM character_usage u
                JOIN characters c ON u.character_id = c.id
                WHERE c.id = ?
            ''', (character_id,))
            usage = cursor.fetchone()
            if usage and usage[1] != user_id:
                self.connection.rollback()
                return False, f"角色「{char_name}」已被其他用户使用"
            
            # 3. 检查用户是否已在使用其他角色
            cursor.execute('''
                SELECT c.char_name 
                FROM character_usage u
                JOIN characters c ON u.character_id = c.id
                WHERE u.user_id = ? AND (u.room_id IS ? OR u.room_id = ?)
            ''', (user_id, room_id, room_id))
            current_usage = cursor.fetchone()
            if current_usage:
                self.connection.rollback()
                return False, f"你当前正在使用角色「{current_usage[0]}」，请先释放当前角色"
            
            # 4. 添加新的使用记录
            cursor.execute('''
                INSERT OR REPLACE INTO character_usage (character_id, user_id, room_id)
                VALUES (?, ?, ?)
            ''', (character_id, user_id, room_id))
            
            # 5. 添加历史记录
            cursor.execute('''
                INSERT INTO character_history (
                    character_id, user_id, room_id, action, 
                    field_name, old_value, new_value, created_at
                ) VALUES (?, ?, ?, 'use', '', '', '', CURRENT_TIMESTAMP)
            ''', (character_id, user_id, room_id))
            
            self.connection.commit()
            return True, f"已切换到角色「{char_name}」"
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"使用角色失败: {e}")
            return False, "使用角色失败，请重试"
    
    def release_character(self, user_id: str, room_id: Optional[str]) -> tuple[bool, str]:
        """释放用户当前使用的角色"""
        try:
            cursor = self.connection.cursor()
            
            # 开始事务
            cursor.execute('BEGIN')
            
            # 获取当前使用的角色
            cursor.execute('''
            SELECT c.id, c.char_name 
            FROM character_usage u
            JOIN characters c ON u.character_id = c.id
            WHERE u.user_id = ? AND (u.room_id IS ? OR u.room_id = ?)
            ''', (user_id, room_id, room_id))
            result = cursor.fetchone()
            
            if not result:
                self.connection.rollback()
                return False, "当前没有使用任何角色"
            
            character_id, char_name = result
            
            # 删除使用记录
            cursor.execute('''
            DELETE FROM character_usage 
            WHERE user_id = ? AND (room_id IS ? OR room_id = ?)
            ''', (user_id, room_id, room_id))
            
            # 添加历史记录
            cursor.execute('''
            INSERT INTO character_history (
                character_id, user_id, room_id, action, 
                field_name, old_value, new_value, created_at
            ) VALUES (?, ?, ?, 'release', '', '', '', CURRENT_TIMESTAMP)
            ''', (character_id, user_id, room_id))
            
            self.connection.commit()
            return True, f"已释放角色「{char_name}」"
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"释放角色失败: {e}")
            return False, "释放角色失败"
    
    def get_active_character(self, user_id: str, room_id: Optional[str]) -> Optional[str]:
        """获取用户当前使用的角色名称"""
        try:
            cursor = self.connection.cursor()
            
            # 修改查询语句，通过 JOIN 获取角色名称
            cursor.execute('''
            SELECT c.char_name
            FROM character_usage u
            JOIN characters c ON u.character_id = c.id
            WHERE u.user_id = ? AND (u.room_id IS ? OR u.room_id = ?)
            ORDER BY u.updated_at DESC
            LIMIT 1
            ''', (user_id, room_id, room_id))
            
            result = cursor.fetchone()
            return result[0] if result else None
        
        except Exception as e:
            logger.error(f"获取当前角色失败: {e}")
            return None

    def get_all_character_usage(self) -> List[Tuple[str, str, str, str]]:
        """获取所有角色卡的使用状态"""
        cursor = self.connection.cursor()
        cursor.execute('''
        SELECT u.char_name, u.user_id, u.room_id, u.updated_at
        FROM character_usage u
        JOIN characters c ON u.char_name = c.char_name
        ORDER BY u.updated_at DESC
        ''')
        return cursor.fetchall()

    def force_release_character(self, char_name: str) -> tuple[bool, str]:
        """强制释放角色卡（管理员功能）"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('DELETE FROM character_usage WHERE char_name = ?', (char_name,))
            self.connection.commit()
            if cursor.rowcount > 0:
                return True, f"已强制释放角色「{char_name}」"
            return False, f"角色「{char_name}」当前未被使用"
        except Exception as e:
            logger.error(f"强制释放角色失败: {e}")
            return False, "强制释放角色失败"

    def get_character_with_usage(self) -> List[dict]:
        """获取所有角色卡及其使用状态"""
        cursor = self.connection.cursor()
        cursor.execute('''
        SELECT c.char_name, c.player_name, c.occupation,
               u.user_id, u.room_id, u.updated_at
        FROM characters c
        LEFT JOIN character_usage u ON c.char_name = u.char_name
        ORDER BY c.char_name
        ''')
        result = cursor.fetchall()
        return [{
            'char_name': row[0],
            'player_name': row[1],
            'occupation': row[2],
            'used_by': row[3],
            'room_id': row[4],
            'used_since': row[5]
        } for row in result]

    def get_character_skills(self, char_name: str) -> tuple[Optional[dict], str]:
        """获取角色的所有技能值"""
        try:
            cursor = self.connection.cursor()
            
            # 首先检查角色是否存在
            cursor.execute('''
            SELECT id FROM characters 
            WHERE char_name = ?
            ''', (char_name,))
            
            character = cursor.fetchone()
            if not character:
                return None, f"未找到角色「{char_name}」"
            
            character_id = character[0]
            
            # 获取所有技能（包括普通技能和自定义技能）
            cursor.execute('''
            SELECT skill_name, base, occupation, interest, growth, is_custom
            FROM character_skills 
            WHERE character_id = ?
            ORDER BY is_custom, skill_name
            ''', (character_id,))
            
            skills = cursor.fetchall()
            
            # 构造返回数据
            result = {
                'skillsList': [],
                'customSkills': []
            }
            
            # 处理普通技能
            for skill in skills:
                skill_name, base, occupation, interest, growth, is_custom = skill
                # 检查是否是带子类型的技能
                if ':' in skill_name:
                    parent_skill, subtype = skill_name.split(':', 1)
                    skill_data = {
                        'name': parent_skill,
                        'base': str(base) if base is not None else '0',
                        'occupation': str(occupation) if occupation is not None else '',
                        'interest': str(interest) if interest is not None else '',
                        'growth': str(growth) if growth is not None else '',
                        'isSubSkill': False,
                        'subtype': subtype
                    }
                else:
                    skill_data = {
                        'name': skill_name,
                        'base': str(base) if base is not None else '0',
                        'occupation': str(occupation) if occupation is not None else '',
                        'interest': str(interest) if interest is not None else '',
                        'growth': str(growth) if growth is not None else '',
                        'isSubSkill': False
                    }
                
                if is_custom:
                    result['customSkills'].append(skill_data)
                else:
                    result['skillsList'].append(skill_data)
            
            return result, ""
            
        except Exception as e:
            logger.error(f"获取角色技能失败: {e}")
            return None, f"获取角色技能失败: {str(e)}"

    def get_growth_points(self, char_name: str) -> int:
        """获取角色的技能成长次数"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('''
            SELECT growth_points 
            FROM characters 
            WHERE char_name = ?
            ''', (char_name,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"获取技能成长次数失败: {e}")
            return 0

    def set_growth_points(self, char_name: str, points: int) -> tuple[bool, str]:
        """设置角色的技能成长次数"""
        try:
            cursor = self.connection.cursor()
            
            # 开始事务
            cursor.execute('BEGIN')
            
            # 获取当前成长点数
            cursor.execute('''
            SELECT growth_points FROM characters 
            WHERE char_name = ?
            ''', (char_name,))
            
            result = cursor.fetchone()
            if not result:
                self.connection.rollback()
                return False, f"未找到角色: {char_name}"
            
            current_points = result[0] or 0
            
            # 更新成长点数
            cursor.execute('''
            UPDATE characters 
            SET growth_points = ? 
            WHERE char_name = ?
            ''', (points, char_name))
            
            # 记录变更历史
            cursor.execute('''
            INSERT INTO character_history (
                character_id, user_id, room_id, action, 
                field_name, old_value, new_value, created_at
            ) VALUES (
                (SELECT id FROM characters WHERE char_name = ?),
                ?, NULL, 'setgrow', 'growth_points', ?, ?, CURRENT_TIMESTAMP
            )
            ''', (char_name, "系统", str(current_points), str(points)))
            
            self.connection.commit()
            return True, f"已设置角色「{char_name}」的成长次数为 {points}"
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"设置技能成长次数失败: {e}")
            return False, "设置成长次数失败"

    def use_growth_point(self, char_name: str) -> tuple[bool, str]:
        """使用一点技能成长次数"""
        try:
            cursor = self.connection.cursor()
            
            # 获取当前成长点数
            cursor.execute('''
            SELECT growth_points 
            FROM characters 
            WHERE char_name = ?
            ''', (char_name,))
            
            result = cursor.fetchone()
            if not result:
                return False, f"未找到角色: {char_name}"
            
            points = result[0]
            if points <= 0:
                return False, "没有可用的成长次数"
            
            # 减少一点成长次数
            cursor.execute('''
            UPDATE characters 
            SET growth_points = growth_points - 1 
            WHERE char_name = ?
            ''', (char_name,))
            
            self.connection.commit()
            return True, f"剩余成长次数: {points - 1}"
            
        except Exception as e:
            logger.error(f"使用技能成长次数失败: {e}")
            return False, "使用成长次数失败"

    def update_skill_growth(self, char_name: str, skill_name: str, growth_value: int) -> bool:
        """更新技能的成长值"""
        try:
            cursor = self.connection.cursor()
            
            # 获取角色ID
            cursor.execute('SELECT id FROM characters WHERE char_name = ?', (char_name,))
            result = cursor.fetchone()
            if not result:
                logger.error(f"未找到角色: {char_name}")
                return False
            
            character_id = result[0]
            
            # 查找技能
            cursor.execute('''
            SELECT id, growth FROM character_skills 
            WHERE character_id = ? AND (
                skill_name = ? OR 
                skill_name = ? OR 
                skill_name LIKE ?
            )
            ''', (
                character_id, 
                skill_name,
                skill_name.lower(),
                f"{skill_name}:%"  # 处理带子类型的技能
            ))
            
            skill = cursor.fetchone()
            if not skill:
                logger.error(f"未找到技能: {skill_name}")
                return False
            
            skill_id, current_growth = skill
            # 如果当前growth为空，设为0
            current_growth = int(current_growth or 0)
            new_growth = current_growth + growth_value
            
            # 更新成长值
            cursor.execute('''
            UPDATE character_skills 
            SET growth = ?, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (new_growth, skill_id))
            
            self.connection.commit()
            return True
            
        except Exception as e:
            logger.error(f"更新技能成长值失败: {e}")
            return False

    def add_character_history(self, char_name: str, user_id: str, room_id: Optional[str], 
                             action: str, field_name: str, old_value: str, new_value: str,
                             points_used: Optional[int] = None) -> bool:
        """添加角色变更历史记录"""
        try:
            cursor = self.connection.cursor()
            
            # 获取角色ID
            cursor.execute('SELECT id FROM characters WHERE char_name = ?', (char_name,))
            result = cursor.fetchone()
            if not result:
                logger.error(f"未找到角色: {char_name}")
                return False
            
            character_id = result[0]
            
            # 添加历史记录
            cursor.execute('''
            INSERT INTO character_history (
                character_id, user_id, room_id, action, 
                field_name, old_value, new_value, points_used, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                character_id, user_id, room_id, action, 
                field_name, old_value, new_value, points_used
            ))
            
            self.connection.commit()
            return True
            
        except Exception as e:
            logger.error(f"添加角色历史记录失败: {e}")
            return False

    @contextmanager
    def get_connection(self):
        """返回单一连接"""
        try:
            yield self.connection
        except Exception as e:
            self.connection.rollback()
            raise e

    def cleanup(self):
        """清理资源"""
        if hasattr(self, 'connection'):
            self.connection.close()

# 创建全局数据库实例
db = Database() 