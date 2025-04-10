#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清空DiceRobot数据库脚本
功能：清空所有表中的数据，但保留表结构
"""

import sqlite3
import os
import sys
from datetime import datetime

# 定义数据库路径
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'characters.db')

# 需要清空的表名列表
TABLES = [
    'characters',
    'character_attributes',
    'character_basic',
    'character_combat',
    'character_growth_history',
    'character_items',
    'character_notes',
    'character_operation_history',
    'character_skills',
    'character_status',
    'character_status_values',
    'character_usage',
    'character_weapons',
    'growth_points'
]

def backup_database():
    """备份数据库"""
    if not os.path.exists(DB_PATH):
        print(f"错误：数据库文件不存在于路径: {DB_PATH}")
        return False
    
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup')
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'characters_{timestamp}.db')
    
    try:
        # 复制数据库文件
        with open(DB_PATH, 'rb') as src, open(backup_path, 'wb') as dst:
            dst.write(src.read())
        print(f"数据库已备份至: {backup_path}")
        return True
    except Exception as e:
        print(f"备份数据库失败: {e}")
        return False

def clear_tables():
    """清空所有表中的数据"""
    try:
        # 连接数据库
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        # 开始事务
        conn.execute("BEGIN TRANSACTION;")
        
        # 清空表数据
        tables_cleared = 0
        for table in TABLES:
            if table in existing_tables:
                print(f"正在清空表: {table}")
                cursor.execute(f"DELETE FROM {table};")
                tables_cleared += 1
            else:
                print(f"警告: 表 {table} 不存在，已跳过")
        
        # 提交事务
        conn.commit()
        print(f"\n成功清空 {tables_cleared} 个表的数据")
        
        # 验证表是否已清空
        for table in TABLES:
            if table in existing_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                print(f"表 {table} 当前包含 {count} 条记录")
        
        # 关闭连接
        cursor.close()
        conn.close()
        return True
    
    except Exception as e:
        print(f"清空表数据时出错: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("DiceRobot 数据库清理工具")
    print("=" * 50)
    print("此工具将清空数据库中所有表的数据，但保留表结构。")
    print(f"数据库路径: {DB_PATH}")
    print("=" * 50)
    
    if not os.path.exists(DB_PATH):
        print(f"错误：数据库文件不存在于路径: {DB_PATH}")
        return
    
    # 确认操作
    confirm = input("警告: 此操作将删除所有角色和技能数据！是否继续? (y/N): ")
    if confirm.lower() != 'y':
        print("操作已取消")
        return
    
    # 再次确认
    confirm_again = input("二次确认: 请输入 'CLEAR' 以确认清空数据库: ")
    if confirm_again != 'CLEAR':
        print("操作已取消")
        return
    
    # 备份数据库
    print("\n正在备份当前数据库...")
    if not backup_database():
        retry = input("备份失败，是否仍要继续? (y/N): ")
        if retry.lower() != 'y':
            print("操作已取消")
            return
    
    # 清空表
    print("\n开始清空数据库表...")
    if clear_tables():
        print("\n数据库清空成功!")
    else:
        print("\n数据库清空过程中出现错误，请检查日志")
    
    print("\n操作完成")

if __name__ == "__main__":
    main() 