# -*- coding: utf-8 -*-
"""
支付状态检测模块
用于实时检测支付状态
"""

import requests
import time
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PaymentStatusChecker:
    """支付状态检测器"""
    
    def __init__(self, db, webhook_url=None):
        """
        初始化支付状态检测器
        
        Args:
            db: 数据库实例
            webhook_url: 支付回调webhook URL（用于第三方支付平台）
        """
        self.db = db
        self.webhook_url = webhook_url
        self.check_interval = 5  # 检测间隔（秒）
    
    def check_payment_status(self, order_id):
        """
        检查单个订单的支付状态
        
        Args:
            order_id: 订单ID
            
        Returns:
            dict: 支付状态信息
        """
        try:
            # 获取订单信息
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, status, payment_id, created_at
                FROM orders
                WHERE id = ?
            ''', (order_id,))
            order = cursor.fetchone()
            
            if not order:
                conn.close()
                return {'success': False, 'message': '订单不存在'}
            
            # 如果订单已完成，直接返回
            if order['status'] in ['paid', 'completed', 'awaiting_confirmation']:
                conn.close()
                return {
                    'success': True,
                    'order_id': order_id,
                    'status': 'completed' if order['status'] in ['paid', 'completed'] else 'pending',
                    'message': '订单已完成' if order['status'] in ['paid', 'completed'] else '等待管理员审核'
                }
            
            # 检查支付记录
            if order['payment_id']:
                cursor.execute('''
                    SELECT id, status, transaction_id, paid_at
                    FROM payments
                    WHERE id = ?
                ''', (order['payment_id'],))
                payment = cursor.fetchone()
                
                if payment and payment['status'] == 'completed':
                    conn.close()
                    return {
                        'success': True,
                        'order_id': order_id,
                        'status': 'completed',
                        'message': '支付已完成'
                    }
            
            conn.close()
            
            # 检查订单是否超时（15分钟）
            created_at = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
            time_diff = (datetime.now() - created_at).total_seconds()
            
            if time_diff > 900:  # 15分钟 = 900秒
                return {
                    'success': True,
                    'order_id': order_id,
                    'status': 'timeout',
                    'message': '订单已超时'
                }
            
            return {
                'success': True,
                'order_id': order_id,
                'status': 'pending',
                'message': '等待支付'
            }
            
        except Exception as e:
            logger.error(f"检查支付状态失败: {str(e)}")
            return {'success': False, 'message': f'检查失败: {str(e)}'}
    
    def check_order_group_payment_status(self, order_group_id):
        """
        检查订单组的支付状态
        
        Args:
            order_group_id: 订单组ID
            
        Returns:
            dict: 支付状态信息
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 获取订单组信息
            cursor.execute('''
                SELECT id, status, total_price, total_items, created_at
                FROM order_groups
                WHERE id = ?
            ''', (order_group_id,))
            order_group = cursor.fetchone()
            
            if not order_group:
                conn.close()
                return {'success': False, 'message': '订单组不存在'}
            
            # 如果订单组已完成，直接返回
            if order_group['status'] in ['paid', 'completed', 'awaiting_confirmation']:
                conn.close()
                return {
                    'success': True,
                    'order_group_id': order_group_id,
                    'status': 'completed' if order_group['status'] in ['paid', 'completed'] else 'pending',
                    'message': '订单已完成' if order_group['status'] in ['paid', 'completed'] else '等待管理员审核'
                }
            
            # 检查订单组下的所有订单状态
            cursor.execute('''
                SELECT id, status
                FROM orders
                WHERE order_group_id = ?
            ''', (order_group_id,))
            orders = cursor.fetchall()
            
            if not orders:
                conn.close()
                return {'success': False, 'message': '订单组下没有订单'}
            
            # 检查是否有订单已完成支付
            all_paid = all(order['status'] in ['paid', 'completed'] for order in orders)
            any_awaiting = any(order['status'] == 'awaiting_confirmation' for order in orders)
            
            if all_paid:
                conn.close()
                return {
                    'success': True,
                    'order_group_id': order_group_id,
                    'status': 'completed',
                    'message': '所有订单已完成支付'
                }
            elif any_awaiting:
                conn.close()
                return {
                    'success': True,
                    'order_group_id': order_group_id,
                    'status': 'pending',
                    'message': '等待管理员审核'
                }
            
            conn.close()
            
            # 检查订单组是否超时（15分钟）
            created_at = datetime.strptime(order_group['created_at'], '%Y-%m-%d %H:%M:%S')
            time_diff = (datetime.now() - created_at).total_seconds()
            
            if time_diff > 900:  # 15分钟 = 900秒
                return {
                    'success': True,
                    'order_group_id': order_group_id,
                    'status': 'timeout',
                    'message': '订单已超时'
                }
            
            return {
                'success': True,
                'order_group_id': order_group_id,
                'status': 'pending',
                'message': '等待支付'
            }
            
        except Exception as e:
            logger.error(f"检查订单组支付状态失败: {str(e)}")
            return {'success': False, 'message': f'检查失败: {str(e)}'}
    
    def verify_payment_from_webhook(self, order_id, transaction_id, amount):
        """
        从webhook验证支付（用于第三方支付平台回调）
        
        Args:
            order_id: 订单ID
            transaction_id: 交易ID
            amount: 支付金额
            
        Returns:
            dict: 验证结果
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 获取订单信息
            cursor.execute('''
                SELECT id, price, status, payment_id
                FROM orders
                WHERE id = ?
            ''', (order_id,))
            order = cursor.fetchone()
            
            if not order:
                conn.close()
                return {'success': False, 'message': '订单不存在'}
            
            # 验证金额
            if float(amount) != float(order['price']):
                conn.close()
                return {'success': False, 'message': '支付金额不匹配'}
            
            # 更新支付状态
            if order['payment_id']:
                success, message = self.db.update_payment_status(
                    order['payment_id'],
                    'completed',
                    transaction_id
                )
                
                if success:
                    conn.commit()
                    conn.close()
                    return {
                        'success': True,
                        'message': '支付验证成功',
                        'order_id': order_id
                    }
                else:
                    conn.close()
                    return {'success': False, 'message': message}
            else:
                conn.close()
                return {'success': False, 'message': '支付记录不存在'}
            
        except Exception as e:
            logger.error(f"验证支付失败: {str(e)}")
            return {'success': False, 'message': f'验证失败: {str(e)}'}
    
    def simulate_payment_success(self, order_id):
        """
        模拟支付成功（用于测试）
        
        Args:
            order_id: 订单ID
            
        Returns:
            dict: 模拟结果
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 获取订单信息
            cursor.execute('''
                SELECT id, price, status, payment_id
                FROM orders
                WHERE id = ?
            ''', (order_id,))
            order = cursor.fetchone()
            
            if not order:
                conn.close()
                return {'success': False, 'message': '订单不存在'}
            
            # 生成模拟交易ID
            transaction_id = f"SIM_{int(time.time())}_{order_id}"
            
            # 更新支付状态
            if order['payment_id']:
                success, message = self.db.update_payment_status(
                    order['payment_id'],
                    'completed',
                    transaction_id
                )
                
                if success:
                    conn.commit()
                    conn.close()
                    logger.info(f"订单 {order_id} 模拟支付成功，交易ID: {transaction_id}")
                    return {
                        'success': True,
                        'message': '模拟支付成功',
                        'order_id': order_id,
                        'transaction_id': transaction_id
                    }
                else:
                    conn.close()
                    return {'success': False, 'message': message}
            else:
                conn.close()
                return {'success': False, 'message': '支付记录不存在'}
            
        except Exception as e:
            logger.error(f"模拟支付失败: {str(e)}")
            return {'success': False, 'message': f'模拟失败: {str(e)}'}
