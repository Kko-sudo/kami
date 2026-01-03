# -*- coding: utf-8 -*-
"""
网站数据库模型
"""

import sqlite3
import hashlib
import json
import os
import logging
from datetime import datetime
from card_key_system import CardKeySystem

logger = logging.getLogger(__name__)

class Database:
    """数据库管理类"""
    
    def __init__(self, db_path='bank_card_system.db'):
        # 优先从环境变量读取数据库路径
        env_db_path = os.environ.get('DATABASE_PATH')
        if env_db_path:
            db_path = env_db_path
        
        # 确保数据库路径是绝对路径
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.getcwd(), db_path)
        
        self.db_path = db_path
        logger.info(f"数据库路径: {self.db_path}")
        
        # 确保数据库目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"创建数据库目录: {db_dir}")
        
        self.init_database()
    
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                raw_password TEXT,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin INTEGER DEFAULT 0,
                first_login INTEGER DEFAULT 1
            )
        ''')
        
        # 卡密表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT NOT NULL,
                card_key TEXT UNIQUE NOT NULL,
                card_type TEXT NOT NULL DEFAULT 'standard',
                days_valid INTEGER DEFAULT 365,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expire_at TIMESTAMP,
                is_used INTEGER DEFAULT 0,
                used_by INTEGER,
                used_at TIMESTAMP,
                price REAL DEFAULT 0.0
            )
        ''')
        
        # 订单表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_key_id INTEGER,
                bank_name TEXT,
                card_type TEXT,
                days_valid INTEGER,
                price REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                order_group_id INTEGER,
                payment_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (card_key_id) REFERENCES card_keys(id),
                FOREIGN KEY (order_group_id) REFERENCES order_groups(id),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            )
        ''')
        
        # 订单组表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total_price REAL NOT NULL,
                total_items INTEGER NOT NULL,
                card_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # 邮件表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sender_id INTEGER,
                subject TEXT NOT NULL,
                content TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (sender_id) REFERENCES users(id)
            )
        ''')
        
        # 用户邮箱表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # 体验卡使用记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trial_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ip_address TEXT NOT NULL,
                device_fingerprint TEXT NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, ip_address, device_fingerprint)
            )
        ''')
        
        # 价格配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_type TEXT UNIQUE NOT NULL,
                price REAL NOT NULL,
                days_valid INTEGER NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 支付表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                payment_method TEXT NOT NULL,
                amount REAL NOT NULL,
                qr_code TEXT,
                status TEXT DEFAULT 'pending',
                transaction_id TEXT,
                paid_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        ''')

        # 插入默认价格配置
        cursor.execute('''
            INSERT OR IGNORE INTO price_config (card_type, price, days_valid, description)
            VALUES (?, ?, ?, ?)
        ''', ('1day', 9.90, 1, '1天体验卡'))
        
        cursor.execute('''
            INSERT OR IGNORE INTO price_config (card_type, price, days_valid, description)
            VALUES (?, ?, ?, ?)
        ''', ('30days', 188.00, 30, '30天月卡'))
        
        # 管理员账户（如果不存在）
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, password, email, is_admin)
            VALUES (?, ?, ?, ?)
        ''', ('XPB13141928629', self.hash_password('xpb@04103013@xpb'), 'admin@axiaowang.com', 1))
        
        # 添加ip_address和device_fingerprint字段（如果不存在）
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN ip_address TEXT')
        except:
            pass
        
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN device_fingerprint TEXT')
        except:
            pass

        # 添加payment_id字段到orders表（如果不存在）
        try:
            cursor.execute('ALTER TABLE orders ADD COLUMN payment_id INTEGER')
        except:
            pass
        
        conn.commit()
        conn.close()
    
    def hash_password(self, password):
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, username, password, email=None, phone=None):
        """创建用户"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO users (username, password, raw_password, email, phone)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, self.hash_password(password), password, email, phone))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return True, user_id
        except sqlite3.IntegrityError:
            conn.close()
            return False, "用户名已存在"
    
    def verify_user(self, username, password):
        """验证用户登录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, password, is_admin, email, phone
            FROM users
            WHERE username = ?
        ''', (username,))
        
        user = cursor.fetchone()
        conn.close()
        
        print(f"[DEBUG] Database verify - Username: {username}, User found: {user is not None}")
        
        if user:
            password_hash = self.hash_password(password)
            print(f"[DEBUG] Password comparison - Input hash: {password_hash}, DB hash: {user['password']}")
            print(f"[DEBUG] Passwords match: {user['password'] == password_hash}")
            
            if user['password'] == password_hash:
                print(f"[DEBUG] User authenticated - ID: {user['id']}, Is Admin: {user['is_admin']}")
                return True, {
                    'id': user['id'],
                    'username': user['username'],
                    'is_admin': bool(user['is_admin']),
                    'email': user['email'],
                    'phone': user['phone']
                }
        
        print(f"[DEBUG] Authentication failed")
        return False, None
    
    def calculate_card_price(self, card_type):
        """计算卡密价格"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT price FROM price_config WHERE card_type = ?
        ''', (card_type,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result['price']
        
        return 0.00
    
    def get_card_type_days(self, card_type):
        """获取卡密类型对应的天数"""
        days_map = {
            '1day': 1,
            '30days': 30
        }
        return days_map.get(card_type, 30)
    
    def generate_card_key(self, bank_name, card_type='standard', days_valid=365, price=0.0):
        """生成卡密"""
        card_system = CardKeySystem()
        
        if card_type != 'standard':
            days_valid = self.get_card_type_days(card_type)
            price = self.calculate_card_price(card_type)
        
        card_key = card_system.generate_card_key(bank_name, days_valid)
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if days_valid == 0:
                cursor.execute('''
                    INSERT INTO card_keys (bank_name, card_key, card_type, days_valid, expire_at, price)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime', '+1 day'), ?)
                ''', (bank_name, card_key, card_type, days_valid, price))
            else:
                cursor.execute('''
                    INSERT INTO card_keys (bank_name, card_key, card_type, days_valid, expire_at, price)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime', '+' || ? || ' days'), ?)
                ''', (bank_name, card_key, card_type, days_valid, days_valid, price))
            conn.commit()
            card_key_id = cursor.lastrowid
            conn.close()
            return True, {'id': card_key_id, 'card_key': card_key}
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_available_card_keys(self, bank_name=None):
        """获取可用的卡密"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if bank_name:
            cursor.execute('''
                SELECT id, bank_name, card_key, price, created_at, expire_at
                FROM card_keys
                WHERE bank_name = ? AND is_used = 0 AND expire_at > datetime('now', 'localtime')
                ORDER BY created_at DESC
            ''', (bank_name,))
        else:
            cursor.execute('''
                SELECT id, bank_name, card_key, price, created_at, expire_at
                FROM card_keys
                WHERE is_used = 0 AND expire_at > datetime('now', 'localtime')
                ORDER BY created_at DESC
            ''')
        
        card_keys = cursor.fetchall()
        conn.close()
        
        return [dict(key) for key in card_keys]
    
    def use_card_key(self, card_key_id, user_id):
        """使用卡密"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE card_keys
                SET is_used = 1, used_by = ?, used_at = datetime('now')
                WHERE id = ? AND is_used = 0
            ''', (user_id, card_key_id))
            
            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                return True, "卡密使用成功"
            else:
                conn.close()
                return False, "卡密不存在或已被使用"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_card_key_by_id(self, card_key_id):
        """根据ID获取卡密"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, bank_name, card_key, price, created_at, expire_at, is_used
            FROM card_keys
            WHERE id = ?
        ''', (card_key_id,))
        
        card_key = cursor.fetchone()
        conn.close()
        
        if card_key:
            return dict(card_key)
        return None
    
    def get_all_card_keys(self):
        """获取所有卡密（管理员用）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, bank_name, card_key, card_type, days_valid, price, created_at, expire_at, is_used, used_by, used_at
            FROM card_keys
            ORDER BY created_at DESC
        ''')
        
        card_keys = cursor.fetchall()
        conn.close()
        
        return [dict(key) for key in card_keys]
    
    def get_statistics(self):
        """获取统计信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 总用户数
        cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 0')
        total_users = cursor.fetchone()['count']
        
        # 总卡密数
        cursor.execute('SELECT COUNT(*) as count FROM card_keys')
        total_card_keys = cursor.fetchone()['count']
        
        # 已使用卡密数
        cursor.execute('SELECT COUNT(*) as count FROM card_keys WHERE is_used = 1')
        used_card_keys = cursor.fetchone()['count']
        
        # 按银行统计
        cursor.execute('''
            SELECT bank_name, COUNT(*) as count
            FROM card_keys
            GROUP BY bank_name
        ''')
        bank_stats = {row['bank_name']: row['count'] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'total_users': total_users,
            'total_card_keys': total_card_keys,
            'used_card_keys': used_card_keys,
            'available_card_keys': total_card_keys - used_card_keys,
            'bank_stats': bank_stats
        }
    
    def create_order(self, user_id, banks, card_type, contact_info='', quantities=None):
        """创建订单（单个订单）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取卡密类型对应的天数和价格
            days_valid = self.get_card_type_days(card_type)
            price = self.calculate_card_price(card_type)
            
            # 只创建单个订单
            bank_name = banks[0] if banks else '未知银行'
            
            # 创建订单记录，card_key_id为NULL，等待管理员生成
            cursor.execute('''
                INSERT INTO orders (user_id, card_key_id, bank_name, card_type, days_valid, price, status, created_at, order_group_id)
                VALUES (?, NULL, ?, ?, ?, ?, 'pending', datetime('now', 'localtime'), NULL)
            ''', (user_id, bank_name, card_type, days_valid, price))
            
            order_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            return True, {'order_id': order_id, 'total_price': price, 'total_items': 1}
        except Exception as e:
            conn.close()
            return False, str(e)

    def purchase_card_key(self, user_id, card_key_id, contact_info=''):
        """购买卡密"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 检查卡密是否可用
            cursor.execute('''
                SELECT id, is_used, expire_at
                FROM card_keys
                WHERE id = ?
            ''', (card_key_id,))
            
            card_key = cursor.fetchone()
            
            if not card_key:
                conn.close()
                return False, "卡密不存在"
            
            if card_key['is_used']:
                conn.close()
                return False, "卡密已被使用"
            
            # 创建订单
            cursor.execute('''
                INSERT INTO orders (user_id, card_key_id, status)
                VALUES (?, ?, 'completed')
            ''', (user_id, card_key_id))
            
            # 标记卡密为已使用
            cursor.execute('''
                UPDATE card_keys
                SET is_used = 1, used_by = ?, used_at = datetime('now')
                WHERE id = ?
            ''', (user_id, card_key_id))
            
            conn.commit()
            conn.close()
            return True, "购买成功"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_user_orders(self, user_id):
        """获取用户订单（单个订单）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 获取所有订单
        cursor.execute('''
            SELECT o.id, o.user_id, o.bank_name, o.card_type, o.days_valid, 
                   o.price, o.status, o.created_at, o.paid_at,
                   c.card_key
            FROM orders o
            LEFT JOIN card_keys c ON o.card_key_id = c.id
            WHERE o.user_id = ?
            ORDER BY o.created_at DESC
        ''', (user_id,))
        
        orders = cursor.fetchall()
        
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                'id': order['id'],
                'order_id': order['id'],
                'bank_name': order['bank_name'],
                'card_type': order['card_type'],
                'days_valid': order['days_valid'],
                'quantity': 1,
                'price': order['price'],
                'total_price': order['price'],
                'created_at': order['created_at'],
                'status': order['status'],
                'card_key': order['card_key'],
                'card_keys': [{'bank_name': order['bank_name'], 'card_key': order['card_key']}] if order['card_key'] else []
            })
        
        conn.close()
        
        return formatted_orders
    
    def get_all_users(self):
        """获取所有用户（管理员用）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, raw_password, email, phone, created_at, is_admin
            FROM users
            ORDER BY created_at DESC
        ''')
        
        users = cursor.fetchall()
        conn.close()
        
        return [dict(user) for user in users]
    
    def get_all_orders(self):
        """获取所有订单（管理员用）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT o.id, o.user_id, o.card_key_id, o.status, o.created_at, o.paid_at,
                   o.bank_name, o.card_type, o.days_valid, o.price,
                   u.username, c.card_key
            FROM orders o
            JOIN users u ON o.user_id = u.id
            LEFT JOIN card_keys c ON o.card_key_id = c.id
            ORDER BY o.created_at DESC
        ''')
        
        orders = cursor.fetchall()
        conn.close()
        
        return [dict(order) for order in orders]
    
    def get_stats(self):
        """获取统计信息（管理员用）"""
        return self.get_statistics()
    
    def delete_card_key(self, card_key_id):
        """删除卡密（管理员用）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM card_keys WHERE id = ?', (card_key_id,))
            conn.commit()
            conn.close()
            return True, "删除成功"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def generate_card_key_for_order(self, order_id):
        """为订单生成卡密"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取订单信息
            cursor.execute('''
                SELECT user_id, bank_name, card_type, days_valid, price
                FROM orders
                WHERE id = ?
            ''', (order_id,))
            
            order = cursor.fetchone()
            if not order:
                conn.close()
                return False, "订单不存在"
            
            user_id = order['user_id']
            bank_name = order['bank_name']
            card_type = order['card_type']
            days_valid = order['days_valid']
            price = order['price']
            
            # 生成卡密
            card_system = CardKeySystem()
            card_key = card_system.generate_card_key(bank_name, days_valid)
            
            # 插入卡密记录
            if days_valid == 0:
                cursor.execute('''
                    INSERT INTO card_keys (bank_name, card_key, card_type, days_valid, expire_at, price)
                    VALUES (?, ?, ?, ?, datetime('now', '+1 day'), ?)
                ''', (bank_name, card_key, card_type, days_valid, price))
            else:
                cursor.execute('''
                    INSERT INTO card_keys (bank_name, card_key, card_type, days_valid, expire_at, price)
                    VALUES (?, ?, ?, ?, datetime('now', '+' || ? || ' days'), ?)
                ''', (bank_name, card_key, card_type, days_valid, days_valid, price))
            
            card_key_id = cursor.lastrowid
            
            # 更新订单，关联卡密
            cursor.execute('''
                UPDATE orders
                SET card_key_id = ?
                WHERE id = ?
            ''', (card_key_id, order_id))
            
            conn.commit()
            conn.close()
            return True, {'card_key_id': card_key_id, 'card_key': card_key}
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def send_email(self, user_id, sender_id, subject, content):
        """发送邮件给用户"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO emails (user_id, sender_id, subject, content)
                VALUES (?, ?, ?, ?)
            ''', (user_id, sender_id, subject, content))
            
            email_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return True, {'email_id': email_id}
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_user_emails(self, user_id, unread_only=False):
        """获取用户的邮件"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if unread_only:
            cursor.execute('''
                SELECT e.id, e.user_id, e.sender_id, e.subject, e.content, e.is_read, e.created_at,
                       u.username as sender_username
                FROM emails e
                LEFT JOIN users u ON e.sender_id = u.id
                WHERE e.user_id = ? AND e.is_read = 0
                ORDER BY e.created_at DESC
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT e.id, e.user_id, e.sender_id, e.subject, e.content, e.is_read, e.created_at,
                       u.username as sender_username
                FROM emails e
                LEFT JOIN users u ON e.sender_id = u.id
                WHERE e.user_id = ?
                ORDER BY e.created_at DESC
            ''', (user_id,))
        
        emails = cursor.fetchall()
        conn.close()
        
        return [dict(email) for email in emails]
    
    def mark_email_as_read(self, email_id, user_id):
        """标记邮件为已读"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE emails
                SET is_read = 1
                WHERE id = ? AND user_id = ?
            ''', (email_id, user_id))
            
            conn.commit()
            conn.close()
            return True, "标记成功"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def add_user_email(self, user_id, email):
        """添加用户邮箱"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO user_emails (user_id, email, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, email))
            
            conn.commit()
            conn.close()
            return True, "邮箱添加成功"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_user_emails_list(self, user_id):
        """获取用户的邮箱列表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, user_id, email, status, created_at
            FROM user_emails
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        
        emails = cursor.fetchall()
        conn.close()
        
        return [dict(email) for email in emails]
    
    def get_all_emails(self):
        """获取所有邮件（管理员用）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT e.id, e.user_id, e.sender_id, e.subject, e.content, e.is_read, e.created_at,
                   u1.username as user_username,
                   u2.username as sender_username
            FROM emails e
            LEFT JOIN users u1 ON e.user_id = u1.id
            LEFT JOIN users u2 ON e.sender_id = u2.id
            ORDER BY e.created_at DESC
        ''')
        
        emails = cursor.fetchall()
        conn.close()
        
        return [dict(email) for email in emails]
    
    def get_user_by_id(self, user_id):
        """根据ID获取用户"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, phone, created_at, is_admin
            FROM users
            WHERE id = ?
        ''', (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return dict(user)
        return None
    
    def check_trial_usage(self, user_id, ip_address, device_fingerprint):
        """检查体验卡是否已使用（设备+账号双重限制）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 检查该用户是否已经使用过体验卡
        cursor.execute('''
            SELECT id, used_at, ip_address, device_fingerprint
            FROM trial_usage
            WHERE user_id = ?
            ORDER BY used_at DESC
            LIMIT 1
        ''', (user_id,))
        
        user_usage = cursor.fetchone()
        if user_usage:
            conn.close()
            return True, {'reason': 'user', 'usage': dict(user_usage)}
        
        # 检查该设备是否已经使用过体验卡（防止换账号）
        cursor.execute('''
            SELECT id, used_at, user_id
            FROM trial_usage
            WHERE ip_address = ? OR device_fingerprint = ?
            ORDER BY used_at DESC
            LIMIT 1
        ''', (ip_address, device_fingerprint))
        
        device_usage = cursor.fetchone()
        if device_usage:
            conn.close()
            return True, {'reason': 'device', 'usage': dict(device_usage)}
        
        conn.close()
        return False, None
    
    def record_trial_usage(self, user_id, ip_address, device_fingerprint):
        """记录体验卡使用"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO trial_usage (user_id, ip_address, device_fingerprint)
                VALUES (?, ?, ?)
            ''', (user_id, ip_address, device_fingerprint))
            
            usage_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return True, {'id': usage_id}
        except sqlite3.IntegrityError:
            conn.close()
            return False, "体验卡已使用"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def check_1day_card_purchase(self, user_id, ip_address, device_fingerprint):
        """检查1天卡密是否已购买（设备+账号双重限制，永久限制）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 检查该用户是否已经购买过1天卡密
        cursor.execute('''
            SELECT id, created_at, card_key
            FROM orders
            WHERE user_id = ? AND card_type = '1day'
            ORDER BY created_at DESC
            LIMIT 1
        ''', (user_id,))
        
        user_order = cursor.fetchone()
        if user_order:
            conn.close()
            return True, {'reason': 'user', 'order': dict(user_order)}
        
        # 检查该设备是否已经购买过1天卡密（防止换账号）
        # 通过IP和User-Agent匹配
        cursor.execute('''
            SELECT o.id, o.created_at, o.card_key, o.user_id
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.card_type = '1day'
            AND (u.ip_address = ? OR u.device_fingerprint = ?)
            ORDER BY o.created_at DESC
            LIMIT 1
        ''', (ip_address, device_fingerprint))
        
        device_order = cursor.fetchone()
        if device_order:
            conn.close()
            return True, {'reason': 'device', 'order': dict(device_order)}
        
        conn.close()
        return False, None
    
    def record_1day_card_purchase(self, user_id, ip_address, device_fingerprint):
        """记录1天卡密购买"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 更新用户的IP和设备指纹
            cursor.execute('''
                UPDATE users SET ip_address = ?, device_fingerprint = ? WHERE id = ?
            ''', (ip_address, device_fingerprint, user_id))
            
            conn.commit()
            conn.close()
            return True, {'user_id': user_id}
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def create_payment(self, order_id, payment_method, amount, qr_code=None):
        """创建支付记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO payments (order_id, payment_method, amount, qr_code, status)
                VALUES (?, ?, ?, ?, 'pending')
            ''', (order_id, payment_method, amount, qr_code))
            
            payment_id = cursor.lastrowid
            
            # 更新订单表
            cursor.execute('''
                UPDATE orders
                SET payment_id = ?
                WHERE id = ?
            ''', (payment_id, order_id))
            
            conn.commit()
            conn.close()
            return True, {'payment_id': payment_id}
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def update_payment_status(self, payment_id, status, transaction_id=None):
        """更新支付状态"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if status == 'completed':
                cursor.execute('''
                    UPDATE payments
                    SET status = ?, transaction_id = ?, paid_at = datetime('now')
                    WHERE id = ?
                ''', (status, transaction_id, payment_id))
                
                # 更新订单状态为已支付
                cursor.execute('''
                    UPDATE orders
                    SET status = 'paid', paid_at = datetime('now')
                    WHERE payment_id = ?
                ''', (payment_id,))
            else:
                cursor.execute('''
                    UPDATE payments
                    SET status = ?, transaction_id = ?
                    WHERE id = ?
                ''', (status, transaction_id, payment_id))
            
            conn.commit()
            conn.close()
            return True, "支付状态更新成功"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_payment_by_order(self, order_id):
        """根据订单ID获取支付记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, order_id, payment_method, amount, status, transaction_id, qr_code, created_at, paid_at
            FROM payments
            WHERE order_id = ?
        ''', (order_id,))
        
        payment = cursor.fetchone()
        conn.close()
        
        if payment:
            return dict(payment)
        return None
    
    def create_email_log(self, user_id, email_address, subject, content):
        """创建邮件发送记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO email_logs (user_id, email_address, subject, content)
                VALUES (?, ?, ?, ?)
            ''', (user_id, email_address, subject, content))
            
            email_log_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return True, {'id': email_log_id}
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def update_email_log(self, email_log_id, status, error_message=None):
        """更新邮件发送记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if status == 'sent':
                cursor.execute('''
                    UPDATE email_logs
                    SET status = ?, sent_at = datetime('now')
                    WHERE id = ?
                ''', (status, email_log_id))
            else:
                cursor.execute('''
                    UPDATE email_logs
                    SET status = ?, error_message = ?
                    WHERE id = ?
                ''', (status, error_message, email_log_id))
            
            conn.commit()
            conn.close()
            return True, "邮件记录更新成功"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_user_by_id(self, user_id):
        """根据ID获取用户信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, phone, created_at, is_admin
            FROM users
            WHERE id = ?
        ''', (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return dict(user)
        return None
    
    def get_all_price_config(self):
        """获取所有价格配置"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, card_type, price, days_valid, description, updated_at
            FROM price_config
            ORDER BY card_type
        ''')
        
        prices = cursor.fetchall()
        conn.close()
        
        return [dict(price) for price in prices]
    
    def update_price_config(self, card_type, price, days_valid=None, description=None):
        """更新价格配置"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if days_valid is not None and description is not None:
                cursor.execute('''
                    UPDATE price_config
                    SET price = ?, days_valid = ?, description = ?, updated_at = datetime('now', 'localtime')
                    WHERE card_type = ?
                ''', (price, days_valid, description, card_type))
            elif days_valid is not None:
                cursor.execute('''
                    UPDATE price_config
                    SET price = ?, days_valid = ?, updated_at = datetime('now', 'localtime')
                    WHERE card_type = ?
                ''', (price, days_valid, card_type))
            elif description is not None:
                cursor.execute('''
                    UPDATE price_config
                    SET price = ?, description = ?, updated_at = datetime('now', 'localtime')
                    WHERE card_type = ?
                ''', (price, description, card_type))
            else:
                cursor.execute('''
                    UPDATE price_config
                    SET price = ?, updated_at = datetime('now', 'localtime')
                    WHERE card_type = ?
                ''', (price, card_type))
            
            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                return True, "价格更新成功"
            else:
                conn.close()
                return False, "卡密类型不存在"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def add_price_config(self, card_type, price, days_valid, description):
        """添加价格配置"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO price_config (card_type, price, days_valid, description)
                VALUES (?, ?, ?, ?)
            ''', (card_type, price, days_valid, description))
            
            conn.commit()
            conn.close()
            return True, "价格配置添加成功"
        except sqlite3.IntegrityError:
            conn.close()
            return False, "卡密类型已存在"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def delete_price_config(self, card_type):
        """删除价格配置"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM price_config WHERE card_type = ?', (card_type,))
            
            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                return True, "价格配置删除成功"
            else:
                conn.close()
                return False, "卡密类型不存在"
        except Exception as e:
            conn.close()
            return False, str(e)

if __name__ == '__main__':
    db = Database()
    
    print("数据库初始化完成")
    print(f"统计信息: {json.dumps(db.get_statistics(), indent=2, ensure_ascii=False)}")
