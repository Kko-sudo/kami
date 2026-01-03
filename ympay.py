# -*- coding: utf-8 -*-
"""
YmPay（源支付Pro）集成模块
"""

import hashlib
import requests
import json
from urllib.parse import urlencode

class YmPay:
    """YmPay（源支付Pro）集成类"""
    
    def __init__(self, pid, key, gateway_url='https://code.ymyu.cn'):
        """
        初始化YmPay
        
        Args:
            pid: 商户ID
            key: 商户密钥
            gateway_url: 支付网关地址
        """
        self.pid = pid
        self.key = key
        self.gateway_url = gateway_url
    
    def create_payment(self, order_id, amount, notify_url, return_url, name='', type=1):
        """
        创建支付订单
        
        Args:
            order_id: 订单ID
            amount: 支付金额
            notify_url: 异步通知地址
            return_url: 同步跳转地址
            name: 商品名称
            type: 支付类型 (1=支付宝, 2=微信支付, 3=QQ钱包)
        
        Returns:
            dict: 包含支付信息或错误信息
        """
        try:
            params = {
                'pid': self.pid,
                'type': type,
                'out_trade_no': str(order_id),
                'notify_url': notify_url,
                'return_url': return_url,
                'name': name,
                'money': str(amount),
                'clientip': '127.0.0.1'
            }
            
            sign = self._generate_sign(params)
            params['sign'] = sign
            
            url = f"{self.gateway_url}/submit.php"
            
            response = requests.post(url, data=params, timeout=30)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                result = response.text
                
                if 'qrcode' in result or 'alipay' in result or 'weixin' in result:
                    return {
                        'success': True,
                        'data': result,
                        'message': '支付订单创建成功'
                    }
                else:
                    return {
                        'success': False,
                        'message': '支付订单创建失败',
                        'response': result
                    }
            else:
                return {
                    'success': False,
                    'message': f'请求失败，状态码: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'创建支付订单失败: {str(e)}'
            }
    
    def verify_notify(self, params):
        """
        验证回调通知
        
        Args:
            params: 回调参数字典
        
        Returns:
            bool: 验证结果
        """
        try:
            sign = params.get('sign', '')
            if not sign:
                return False
            
            params_copy = params.copy()
            params_copy.pop('sign', None)
            params_copy.pop('sign_type', None)
            
            generated_sign = self._generate_sign(params_copy)
            
            return sign == generated_sign
            
        except Exception as e:
            print(f"验证回调失败: {str(e)}")
            return False
    
    def _generate_sign(self, params):
        """
        生成签名
        
        Args:
            params: 参数字典
        
        Returns:
            str: 签名字符串
        """
        keys = sorted(params.keys())
        sign_str = '&'.join([f"{k}={params[k]}" for k in keys if params[k] != ''])
        sign_str += f"&key={self.key}"
        
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    
    def query_payment(self, order_id):
        """
        查询订单状态
        
        Args:
            order_id: 订单ID
        
        Returns:
            dict: 订单状态信息
        """
        try:
            params = {
                'pid': self.pid,
                'out_trade_no': str(order_id)
            }
            
            sign = self._generate_sign(params)
            params['sign'] = sign
            
            url = f"{self.gateway_url}/query.php"
            
            response = requests.post(url, data=params, timeout=30)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'message': f'查询失败，状态码: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'查询订单状态失败: {str(e)}'
            }


class YmPayConfig:
    """YmPay配置类"""
    
    def __init__(self):
        self.pid = None
        self.key = None
        self.gateway_url = 'https://code.ymyu.cn'
        self.notify_url = None
        self.return_url = None
        self.load_config()
    
    def load_config(self):
        """加载配置"""
        try:
            import os
            config_file = os.path.join(os.path.dirname(__file__), 'ympay_config.json')
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.pid = config.get('pid')
                    self.key = config.get('key')
                    self.gateway_url = config.get('gateway_url', 'https://code.ymyu.cn')
                    self.notify_url = config.get('notify_url')
                    self.return_url = config.get('return_url')
        except Exception as e:
            print(f"加载YmPay配置失败: {str(e)}")
    
    def save_config(self):
        """保存配置"""
        try:
            import os
            config_file = os.path.join(os.path.dirname(__file__), 'ympay_config.json')
            
            config = {
                'pid': self.pid,
                'key': self.key,
                'gateway_url': self.gateway_url,
                'notify_url': self.notify_url,
                'return_url': self.return_url
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"保存YmPay配置失败: {str(e)}")
            return False
    
    def get_ympay_instance(self):
        """获取YmPay实例"""
        if not self.pid or not self.key:
            raise Exception("YmPay配置不完整，请先设置pid和key")
        
        return YmPay(
            pid=self.pid,
            key=self.key,
            gateway_url=self.gateway_url
        )
