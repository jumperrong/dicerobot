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
from backup_manager import BackupManager

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
        
        # 初始化备份管理器
        self.backup_manager = BackupManager(self.db_path)
        # 启动自动备份
        self.backup_manager.start_auto_backup()
    
    def _ensure_db_dir(self) -> str:
        """确保数据库目录存在"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(current_dir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'characters.db')
    
    def _init_db(self):
        """初始化数据库表结构"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # 创建角色表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS characters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        char_name TEXT UNIQUE,
                        data TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 创建角色状态表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_status (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER,
                        user_id TEXT,
                        room_id TEXT,
                        status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (character_id) REFERENCES characters (id),
                        UNIQUE(user_id, room_id)
                    )
                ''')
                
                # 创建角色操作历史表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_operation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_name TEXT,
                        user_id TEXT,
                        action TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 创建角色成长历史表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_growth_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_name TEXT,
                        user_id TEXT,
                        action TEXT,
                        field_name TEXT,
                        old_value TEXT,
                        new_value TEXT,
                        points_used INTEGER,
                        check_roll TEXT,
                        growth_roll TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 创建成长点数表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS growth_points (
                        character_name TEXT PRIMARY KEY,
                        points INTEGER DEFAULT 0
                    )
                ''')
                
                # 创建角色基础信息表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_basic (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        characterName TEXT NOT NULL,
                        playerName TEXT,
                        occupation TEXT,
                        age TEXT,
                        gender TEXT,
                        residence TEXT,
                        birthplace TEXT,
                        era TEXT,
                        is_partner BOOLEAN DEFAULT 0,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 创建角色属性表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_attributes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        str INTEGER,
                        con INTEGER,
                        siz INTEGER,
                        dex INTEGER,
                        app INTEGER,
                        int INTEGER,
                        pow INTEGER,
                        edu INTEGER,
                        luc INTEGER,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 创建角色技能表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_skills (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        skill_name TEXT NOT NULL,
                        base INTEGER,
                        occupation INTEGER,
                        interest INTEGER,
                        growth INTEGER,
                        is_custom BOOLEAN DEFAULT 0,
                        subtype TEXT,
                        FOREIGN KEY (character_id) REFERENCES characters(id),
                        UNIQUE(character_id, skill_name, subtype)
                    )
                ''')
                
                # 创建角色状态值表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_status_values (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        category TEXT NOT NULL,
                        type TEXT NOT NULL,
                        value TEXT,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 创建角色物品表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        item_name TEXT NOT NULL,
                        type TEXT,
                        description TEXT,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 创建角色武器表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_weapons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        weapon_name TEXT NOT NULL,
                        damage TEXT,
                        feature TEXT,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 创建角色笔记表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT,
                        type TEXT,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 创建角色战斗数据表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_combat (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id INTEGER NOT NULL,
                        damage_bonus TEXT,
                        spirit_bonus TEXT,
                        build TEXT,
                        armor TEXT,
                        other_combat_data TEXT,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 创建角色使用状态表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS character_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        character_id INTEGER NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (character_id) REFERENCES characters(id)
                    )
                ''')
                
                # 检查 character_growth_history 表是否已存在 check_roll 和 growth_roll 列
                cursor.execute("PRAGMA table_info(character_growth_history)")
                columns = [column[1] for column in cursor.fetchall()]
                
                # 如果 check_roll 列不存在，添加它
                if 'check_roll' not in columns:
                    cursor.execute('''
                        ALTER TABLE character_growth_history
                        ADD COLUMN check_roll TEXT
                    ''')
                
                # 如果 growth_roll 列不存在，添加它
                if 'growth_roll' not in columns:
                    cursor.execute('''
                        ALTER TABLE character_growth_history
                        ADD COLUMN growth_roll TEXT
                    ''')
                
                conn.commit()
                logger.info("数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}", exc_info=True)
            raise

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
            
            # 开始事务
            cursor.execute('BEGIN')
            logger.debug(f"开始保存角色数据: {char_data.get('basic', {}).get('characterName')}")
            
            # 获取角色名称
            char_name = char_data.get('basic', {}).get('characterName')
            
            # 检查是否存在同名角色
            cursor.execute('SELECT id FROM characters WHERE char_name = ?', (char_name,))
            existing_result = cursor.fetchone()
            
            character_id = None
            is_update = False
            
            if existing_result:
                # 如果存在同名角色，使用现有角色ID
                character_id = existing_result[0]
                is_update = True
                logger.debug(f"找到现有角色 ID: {character_id}，进行更新操作")
            
            # 1. 保存/更新基本信息
            basic = char_data.get('basic', {})
            
            if is_update:
                # 更新现有角色记录
                cursor.execute('''
                UPDATE characters SET 
                    player_name = ?, 
                    occupation = ?, 
                    age = ?, 
                    gender = ?, 
                    residence = ?, 
                    birthplace = ?, 
                    era = ?, 
                    is_partner = ?
                WHERE id = ?
                ''', (
                    basic.get('playerName'),
                    basic.get('occupation'),
                    basic.get('age'),
                    basic.get('gender'),
                    basic.get('residence'),
                    basic.get('birthplace'),
                    basic.get('era'),
                    basic.get('isPartner', False),
                    character_id
                ))
            else:
                # 创建新的角色记录
                cursor.execute('''
                INSERT INTO characters (
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
                
                # 获取新插入的角色ID
                character_id = cursor.lastrowid
            
            logger.debug(f"保存基本信息完成，角色ID: {character_id}")
            
            # 2. 保存属性值
            if 'attributes' in char_data:
                logger.debug("开始保存属性数据")
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
                logger.debug("属性数据保存完成")
            
            # 3. 保存状态数据
            if 'status' in char_data:
                logger.debug("开始保存状态数据")
                cursor.execute('DELETE FROM character_status WHERE character_id = ?', (character_id,))
                status = char_data['status']
                for category, values in status.items():  # sanity, health, magic
                    for type_, value in values.items():  # current, start, max, temp
                        cursor.execute('''
                        INSERT INTO character_status (
                            character_id, category, type, value
                        ) VALUES (?, ?, ?, ?)
                        ''', (character_id, category, type_, value))
                logger.debug("状态数据保存完成")
            
            # 4. 保存技能数据
            if 'skills' in char_data and 'skillsList' in char_data['skills']:
                logger.debug("开始保存技能数据")
                # 删除该角色的所有技能记录（包括普通技能和自定义技能）
                cursor.execute('DELETE FROM character_skills WHERE character_id = ?', (character_id,))
                
                # 保存普通技能
                for skill in char_data['skills']['skillsList']:
                    if not skill.get('isSubSkill'):
                        # 如果技能有子类型，使用 "技能:子类型" 格式保存
                        if 'subtype' in skill and skill['subtype']:
                            skill_name = f"{skill['name']}:{skill['subtype']}"
                        else:
                            skill_name = skill['name']
                        
                        cursor.execute('''
                        INSERT OR REPLACE INTO character_skills (
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
                logger.debug("普通技能保存完成")
            
            # 5. 保存自定义技能
            if 'customSkills' in char_data:
                logger.debug("开始保存自定义技能")
                for skill in char_data['customSkills']:
                    cursor.execute('''
                    INSERT OR REPLACE INTO character_skills (
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
                logger.debug("自定义技能保存完成")
            
            # 6. 保存物品数据
            if 'items' in char_data:
                logger.debug("开始保存物品数据")
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
                logger.debug("物品数据保存完成")
            
            # 7. 保存武器数据
            if 'weapons' in char_data:
                logger.debug("开始保存武器数据")
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
                logger.debug("武器数据保存完成")
            
            # 7.5 保存战斗数据
            if 'combat' in char_data:
                logger.debug("开始保存战斗数据")
                cursor.execute('DELETE FROM character_combat WHERE character_id = ?', (character_id,))
                combat = char_data['combat']
                cursor.execute('''
                INSERT INTO character_combat (
                    character_id, damage_bonus, spirit_bonus, build, armor, other_combat_data
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    character_id,
                    combat.get('damageBonus', ''),
                    combat.get('spiritBonus', ''),
                    combat.get('build', ''),
                    combat.get('armor', ''),
                    json.dumps(combat)  # 存储完整的combat数据作为JSON
                ))
                logger.debug("战斗数据保存完成")
            
            # 8. 保存笔记数据
            if 'notes' in char_data:
                logger.debug("开始保存笔记数据")
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
                logger.debug("笔记数据保存完成")
            
            # 提交事务
            self.connection.commit()
            logger.debug("所有数据保存完成，事务已提交")
            return True, f"角色「{basic.get('characterName')}」保存成功"
            
        except Exception as e:
            # 发生错误时回滚事务
            self.connection.rollback()
            logger.error(f"保存角色数据失败: {e}")
            return False, f"保存角色数据失败: {str(e)}"
    
    def get_character(self, char_name: str) -> Optional[dict]:
        """获取角色卡数据"""
        try:
            cursor = self.connection.cursor()
            
            # 获取基本字段
            cursor.execute('''
            SELECT 
                c.id, c.char_name, c.player_name, c.occupation, c.age, 
                c.gender, c.residence, c.birthplace, c.era,
                ca.str, ca.con, ca.siz, ca.dex, ca.app, ca.int, ca.pow, ca.edu, ca.luc, ca.san, ca.hp, ca.mp
            FROM characters c
            LEFT JOIN character_attributes ca ON c.id = ca.character_id
            WHERE c.char_name = ?
            ''', (char_name,))
            
            basic_result = cursor.fetchone()
            if not basic_result:
                return None
                
            character_id = basic_result[0]
            
            # 获取状态数据
            cursor.execute('''
            SELECT category, type, value 
            FROM character_status 
            WHERE character_id = ?
            ''', (character_id,))
            status_rows = cursor.fetchall()
            status_data = self._format_status_data(status_rows)
            
            # 获取物品数据
            cursor.execute('''
            SELECT item_name, type, description 
            FROM character_items 
            WHERE character_id = ?
            ''', (character_id,))
            items_rows = cursor.fetchall()
            items_data = [{'name': row[0], 'type': row[1], 'note': row[2]} for row in items_rows]
            
            # 获取武器数据
            cursor.execute('''
            SELECT weapon_name, damage, features 
            FROM character_weapons 
            WHERE character_id = ?
            ''', (character_id,))
            weapons_rows = cursor.fetchall()
            weapons_data = [{'name': row[0], 'damage': row[1], 'features': row[2]} for row in weapons_rows if row[0]]
            
            # 获取笔记数据
            cursor.execute('''
            SELECT title, content 
            FROM character_notes 
            WHERE character_id = ?
            ''', (character_id,))
            notes_rows = cursor.fetchall()
            notes_data = [{'name': row[0], 'note': row[1]} for row in notes_rows]
            
            # 获取自定义技能
            cursor.execute('''
            SELECT skill_name, base, occupation, interest, growth
            FROM character_skills
            WHERE character_id = ? AND is_custom = 1
            ''', (character_id,))
            custom_skills_rows = cursor.fetchall()
            custom_skills = []
            for row in custom_skills_rows:
                custom_skills.append({
                    'name': row[0],
                    'base': row[1],
                    'occupation': row[2],
                    'interest': row[3],
                    'growth': row[4]
                })
            
            # 获取战斗数据
            cursor.execute('''
            SELECT damage_bonus, spirit_bonus, build, armor, other_combat_data
            FROM character_combat
            WHERE character_id = ?
            ''', (character_id,))
            combat_row = cursor.fetchone()
            combat_data = {}
            
            if combat_row:
                combat_data = {
                    'damageBonus': combat_row[0] or '',
                    'spiritBonus': combat_row[1] or '',
                    'build': combat_row[2] or '',
                    'armor': combat_row[3] or ''
                }
                # 解析其他战斗数据
                if combat_row[4]:
                    try:
                        additional_combat = json.loads(combat_row[4])
                        for key, value in additional_combat.items():
                            if key not in ['damageBonus', 'spiritBonus', 'build', 'armor']:
                                combat_data[key] = value
                    except:
                        pass
            
            # 构建角色卡数据
            return {
                'basic': {
                    'characterName': basic_result[1],
                    'playerName': basic_result[2],
                    'occupation': basic_result[3],
                    'age': basic_result[4],
                    'gender': basic_result[5], 
                    'residence': basic_result[6],
                    'birthplace': basic_result[7],
                    'era': basic_result[8]
                },
                'attributes': {
                    'str': str(basic_result[9] or 0),
                    'con': str(basic_result[10] or 0),
                    'siz': str(basic_result[11] or 0),
                    'dex': str(basic_result[12] or 0),
                    'app': str(basic_result[13] or 0),
                    'int': str(basic_result[14] or 0),
                    'pow': str(basic_result[15] or 0),
                    'edu': str(basic_result[16] or 0),
                    'luc': str(basic_result[17] or 0),
                    'san': str(basic_result[18] or 0),
                    'hp': str(basic_result[19] or 0),
                    'mp': str(basic_result[20] or 0)
                },
                'status': status_data,
                'items': items_data,
                'notes': notes_data,
                'weapons': weapons_data,
                'combat': combat_data,
                'customSkills': custom_skills
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
            
            # 获取战斗数据
            cursor.execute('''
            SELECT damage_bonus, spirit_bonus, build, armor, other_combat_data
            FROM character_combat
            WHERE character_id = ?
            ''', (character_id,))
            combat_data = cursor.fetchone()
            combat_info = {}
            
            if combat_data:
                combat_info = {
                    'damageBonus': combat_data[0] or '',
                    'spiritBonus': combat_data[1] or '',
                    'build': combat_data[2] or '',
                    'armor': combat_data[3] or ''
                }
                # 如果有更多战斗数据，从JSON中解析
                if combat_data[4]:
                    try:
                        additional_combat = json.loads(combat_data[4])
                        # 更新combat_info，保留所有额外的字段
                        for key, value in additional_combat.items():
                            if key not in ['damageBonus', 'spiritBonus', 'build', 'armor']:
                                combat_info[key] = value
                    except:
                        pass
            
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
                } for weapon in weapons_data if weapon[0]],
                'combat': combat_info
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
    
    def format_operation_history(self, history_records: list) -> str:
        """格式化操作历史记录的展示"""
        if not history_records:
            return "暂无操作记录"
        
        formatted = []
        for record in history_records:
            created_at, user_id, action = record[0], record[1], record[2]
            # 格式化时间
            time_str = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
            
            # 格式化操作类型
            action_desc = {
                'create': '创建',
                'use': '使用',
                'release': '释放',
                'overwrite': '覆盖'
            }.get(action, action)
            
            formatted.append(f"{time_str} {user_id} {action_desc}")
        
        return "\n".join(formatted)

    def format_growth_history(self, history_records: list) -> str:
        """格式化成长历史记录，用于展示"""
        if not history_records:
            return "📊 没有成长历史记录"
            
        result = "📊 成长历史记录：\n"
        for record in history_records:
            # 获取时间、用户、动作和字段
            time_str = record['created_at']
            user_id = record['user_id']
            action = record['action']
            field_name = record['field_name']
            old_value = record['old_value']
            new_value = record['new_value']
            points_used = record['points_used']
            check_roll = record['check_roll']
            growth_roll = record['growth_roll']
            
            # 动作图标
            if action == "grow":
                action_icon = "📈"
            elif action == "setgrow":
                action_icon = "⚙️"
            else:
                action_icon = "🔄"
                
            # 成长点数使用信息
            points_info = ""
            if points_used is not None and points_used > 0:
                points_info = f"（消耗{points_used}点）"
                
            # 骰值信息
            roll_info = ""
            if check_roll and growth_roll:
                roll_info = f"\n   🎲 检定：{check_roll} | 成长：{growth_roll}"
                
            # 成长量计算
            growth_amount = ""
            if old_value and new_value and action == "grow":
                try:
                    old_val = int(old_value)
                    new_val = int(new_value)
                    growth_amount = f"增长了 {new_val - old_val} 点"
                except:
                    growth_amount = ""
            
            # 格式化记录
            if field_name == "growth_points":
                # 成长点数变化记录
                result += f"{action_icon} {time_str} | {user_id} 将成长点数从 {old_value} 调整为 {new_value}\n"
            else:
                # 技能成长记录
                result += f"{action_icon} {time_str} | {user_id} 的 {field_name} 技能从 {old_value} 成长到 {new_value} {growth_amount} {points_info}{roll_info}\n"
                
        return result

    def get_current_character(self, user_id: str) -> Optional[tuple[int, str]]:
        """获取用户当前使用的角色"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('''
            SELECT c.id, c.char_name 
            FROM characters c
            JOIN character_usage u ON c.id = u.character_id
            WHERE u.user_id = ?
            ORDER BY u.updated_at DESC
            LIMIT 1
            ''', (user_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取当前角色失败: {e}")
            return None

    def use_character(self, user_id: str, char_name: str) -> tuple[bool, str]:
        """使用角色"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('BEGIN')
            
            # 获取角色ID
            cursor.execute('SELECT id FROM characters WHERE char_name = ?', (char_name,))
            result = cursor.fetchone()
            if not result:
                self.connection.rollback()
                return False, f"未找到角色: {char_name}"
            
            character_id = result[0]
            
            # 更新使用记录
            cursor.execute('''
            INSERT OR REPLACE INTO character_usage 
            (user_id, character_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, character_id))
            
            self.connection.commit()
            return True, f"已切换到角色「{char_name}」"
        except Exception as e:
            self.connection.rollback()
            logger.error(f"使用角色失败: {e}")
            return False, "使用角色失败"

    def release_character(self, user_id: str) -> tuple[bool, str]:
        """释放用户当前使用的角色"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('BEGIN')
            
            # 获取当前角色
            current = self.get_current_character(user_id)
            if not current:
                self.connection.rollback()
                return False, "当前未使用任何角色"
            
            char_id, char_name = current
            
            # 删除使用记录
            cursor.execute('''
            DELETE FROM character_usage 
            WHERE user_id = ? AND character_id = ?
            ''', (user_id, char_id))
            
            self.connection.commit()
            return True, f"已释放角色「{char_name}」"
        except Exception as e:
            self.connection.rollback()
            logger.error(f"释放角色失败: {e}")
            return False, "释放角色失败"

    def get_character_users(self, char_name: str) -> list:
        """获取正在使用该角色的用户列表"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('''
            SELECT u.user_id
            FROM character_usage u
            JOIN characters c ON u.character_id = c.id
            WHERE c.char_name = ?
            ''', (char_name,))
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取角色使用者失败: {e}")
            return []

    def get_active_character(self, user_id: str, room_id: Optional[str]) -> Optional[str]:
        """获取用户当前使用的角色名称"""
        try:
            cursor = self.connection.cursor()
            
            # 修改查询语句，移除 room_id 相关条件
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

    def get_all_character_usage(self) -> List[Tuple[str, str, str]]:
        """获取所有角色卡的使用状态"""
        cursor = self.connection.cursor()
        cursor.execute('''
        SELECT c.char_name, u.user_id, u.updated_at
        FROM character_usage u
        JOIN characters c ON u.character_id = c.id
        ORDER BY u.updated_at DESC
        ''')
        return cursor.fetchall()

    def force_release_character(self, char_name: str) -> tuple[bool, str]:
        """强制释放角色卡（管理员功能）"""
        try:
            cursor = self.connection.cursor()
            
            # 首先查找角色ID
            cursor.execute('SELECT id FROM characters WHERE char_name = ?', (char_name,))
            result = cursor.fetchone()
            if not result:
                return False, f"未找到角色: {char_name}"
            
            character_id = result[0]
            
            # 删除该角色的所有使用记录
            cursor.execute('DELETE FROM character_usage WHERE character_id = ?', (character_id,))
            self.connection.commit()
            
            if cursor.rowcount > 0:
                return True, f"已强制释放角色「{char_name}」"
            return False, f"角色「{char_name}」当前未被使用"
        except Exception as e:
            logger.error(f"强制释放角色失败: {e}")
            return False, "强制释放角色失败"

    def get_character_with_usage(self) -> List[Dict[str, Any]]:
        """获取所有角色卡及其使用状态"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        c.char_name,
                        c.player_name,
                        c.occupation,
                        u.user_id as used_by,
                        u.updated_at
                    FROM characters c
                    LEFT JOIN character_usage u ON c.id = u.character_id
                    ORDER BY c.char_name
                """)
                rows = cursor.fetchall()
                
                # 将结果转换为字典列表，移除 room_id
                return [{
                    'char_name': row[0],
                    'player_name': row[1],
                    'occupation': row[2],
                    'used_by': row[3],
                    'updated_at': row[4]
                } for row in rows]
                
        except Exception as e:
            logger.error(f"获取角色列表失败: {e}")
            return []

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
            logger.debug(f"获取角色技能: {char_name} (ID: {character_id})")
            
            # 获取所有技能（包括普通技能和自定义技能）
            cursor.execute('''
            SELECT skill_name, base, occupation, interest, growth, is_custom
            FROM character_skills 
            WHERE character_id = ?
            ORDER BY is_custom, skill_name
            ''', (character_id,))
            
            skills = cursor.fetchall()
            logger.debug(f"找到 {len(skills)} 个技能")
            
            # 构造返回数据
            result = {
                'skillsList': [],
                'customSkills': []
            }
            
            # 处理普通技能
            for skill in skills:
                skill_name, base, occupation, interest, growth, is_custom = skill
                logger.debug(f"处理技能: {skill_name} (base={base}, occupation={occupation}, interest={interest}, growth={growth}, is_custom={is_custom})")
                
                # 检查是否是带子类型的技能
                if ':' in skill_name:
                    parent_skill, subtype = skill_name.split(':', 1)
                    logger.debug(f"拆分技能名: {parent_skill} -> {subtype}")
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
            
            logger.debug(f"普通技能: {len(result['skillsList'])}个, 自定义技能: {len(result['customSkills'])}个")
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
            
            # 移除这里的变更历史记录，由CharacterManager负责
            
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

    def update_skill_growth(
        self, 
        char_name: str, 
        skill_name: str, 
        growth_value: int, 
        user_id: str = "系统", 
        points_used: int = 1,
        check_roll: str = None,
        growth_roll: str = None
    ) -> bool:
        """
        更新技能成长值
        
        Args:
            char_name: 角色名
            skill_name: 技能名
            growth_value: 成长值
            user_id: 用户ID
            points_used: 使用的成长点数
            check_roll: 检定骰值
            growth_roll: 成长骰值
            
        Returns:
            bool: 是否更新成功
        """
        try:
            cursor = self.connection.cursor()
            
            # 获取角色ID
            cursor.execute('''
            SELECT id FROM characters WHERE char_name = ?
            ''', (char_name,))
            character_result = cursor.fetchone()
            if not character_result:
                logger.error(f"角色不存在: {char_name}")
                return False
            
            character_id = character_result[0]
            
            # 检查是否为普通技能
            cursor.execute('''
            SELECT id, growth FROM character_skills 
            WHERE character_id = ? AND skill_name = ?
            ''', (character_id, skill_name))
            
            skill_result = cursor.fetchone()
            
            # 如果找不到技能，尝试在自定义技能中查找
            if not skill_result:
                cursor.execute('''
                SELECT id, growth FROM character_skills 
                WHERE character_id = ? AND skill_name = ? AND is_custom = 1
                ''', (character_id, skill_name))
                skill_result = cursor.fetchone()
                
                # 如果还是找不到，尝试作为带子类型的技能查找（格式 "技能名:子类型"）
                if not skill_result and ':' in skill_name:
                    main_skill = skill_name.split(':', 1)[0]
                    cursor.execute('''
                    SELECT id, growth FROM character_skills 
                    WHERE character_id = ? AND skill_name = ?
                    ''', (character_id, main_skill))
                    skill_result = cursor.fetchone()
                
                # 如果还是找不到，那么这个技能确实不存在
                if not skill_result:
                    logger.error(f"技能不存在: {skill_name}")
                    return False
            
            skill_id, current_growth = skill_result
            
            # 如果当前growth为空，默认为0
            if current_growth is None:
                current_growth = 0
            else:
                try:
                    current_growth = int(current_growth)
                except ValueError:
                    current_growth = 0
            
            # 计算新的growth值
            new_growth = current_growth + growth_value
            
            # 直接更新技能的growth值
            cursor.execute('''
            UPDATE character_skills SET growth = ? WHERE id = ?
            ''', (new_growth, skill_id))
            
            # 提交更改
            self.connection.commit()
            
            # 获取当前技能总值
            cursor.execute('''
            SELECT base, occupation, interest, growth FROM character_skills WHERE id = ?
            ''', (skill_id,))
            skill_data = cursor.fetchone()
            
            base = int(skill_data[0] or 0)
            occupation = int(skill_data[1] or 0)
            interest = int(skill_data[2] or 0)
            growth = int(skill_data[3] or 0)
            
            current_skill_value = base + occupation + interest + (current_growth or 0)
            new_skill_value = base + occupation + interest + new_growth
            
            # 记录成长历史
            self.add_growth_history(
                char_name, 
                user_id, 
                "grow", 
                skill_name, 
                str(current_skill_value), 
                str(new_skill_value), 
                points_used,
                check_roll,
                growth_roll
            )
            
            logger.info(f"成功为角色 {char_name} 的技能 {skill_name} 增加成长值 {growth_value}")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"更新技能成长值失败: {e}", exc_info=True)
            return False

    def add_operation_history(self, char_name: str, user_id: str, action: str):
        """记录角色操作历史（创建、使用、释放等）"""
        try:
            cursor = self.connection.cursor()
            # 使用Python的datetime生成当前确切时间
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
            INSERT INTO character_operation_history (
                character_name, user_id, action, created_at
            ) VALUES (?, ?, ?, ?)
            ''', (char_name, user_id, action, current_time))
            self.connection.commit()
            logger.debug(f"记录操作历史: {char_name} - {action}")
        except Exception as e:
            logger.error(f"记录操作历史失败: {e}")

    def get_character_operation_history(self, char_name: str, limit: int = 50) -> list:
        """获取角色卡操作历史（创建、使用、释放等）"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('''
            SELECT created_at, user_id, action
            FROM character_operation_history
            WHERE character_name = ?
            ORDER BY created_at DESC
            LIMIT ?
            ''', (char_name, limit))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取角色操作历史失败: {e}", exc_info=True)
            return []

    def get_character_growth_history(self, char_name: str, limit: int = 20) -> list:
        """获取角色成长历史记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, character_name, user_id, action, field_name, 
                           old_value, new_value, points_used, check_roll, growth_roll, created_at 
                    FROM character_growth_history 
                    WHERE character_name = ? 
                    ORDER BY id DESC 
                    LIMIT ?
                ''', (char_name, limit))
                
                history = cursor.fetchall()
                result = []
                for record in history:
                    result.append({
                        'id': record[0],
                        'char_name': record[1],
                        'user_id': record[2],
                        'action': record[3],
                        'field_name': record[4],
                        'old_value': record[5],
                        'new_value': record[6],
                        'points_used': record[7],
                        'check_roll': record[8],
                        'growth_roll': record[9],
                        'created_at': record[10]
                    })
                return result
                
        except Exception as e:
            logger.error(f"获取角色成长历史记录失败: {e}", exc_info=True)
            return []

    def add_growth_history(self, char_name: str, user_id: str, 
                          action: str, field_name: str, old_value: str, 
                          new_value: str, points_used: int = None,
                          check_roll: str = None, growth_roll: str = None):
        """
        添加角色成长历史记录
        
        Args:
            char_name: 角色名
            user_id: 用户ID
            action: 动作描述
            field_name: 成长的字段名
            old_value: 旧值
            new_value: 新值
            points_used: 使用的成长点数
            check_roll: 检定骰值
            growth_roll: 成长骰值
        """
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO character_growth_history 
                    (character_name, user_id, created_at, action, field_name, old_value, new_value, points_used, check_roll, growth_roll) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (char_name, user_id, current_time, action, field_name, old_value, new_value, points_used, check_roll, growth_roll))
                conn.commit()
        except Exception as e:
            logger.error(f"添加角色成长历史记录失败: {e}", exc_info=True)

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
        # 停止自动备份
        if hasattr(self, 'backup_manager'):
            self.backup_manager.stop_auto_backup()

    def create_backup(self, backup_name: Optional[str] = None) -> str:
        """
        创建数据库备份
        
        Args:
            backup_name: 备份文件名，如果不指定则使用时间戳
            
        Returns:
            str: 备份文件路径
        """
        return self.backup_manager.create_backup(backup_name)
    
    def restore_backup(self, backup_path: str) -> bool:
        """
        从备份文件恢复数据库
        
        Args:
            backup_path: 备份文件路径
            
        Returns:
            bool: 是否恢复成功
        """
        return self.backup_manager.restore_backup(backup_path)
    
    def list_backups(self) -> List[str]:
        """
        列出所有备份文件
        
        Returns:
            List[str]: 备份文件路径列表
        """
        return self.backup_manager.list_backups()

# 创建全局数据库实例
db = Database() 