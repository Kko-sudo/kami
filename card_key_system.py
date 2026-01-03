# -*- coding: utf-8 -*-
"""
卡密系统模块
用于生成和验证高安全性的卡密
"""

import hashlib
import secrets
import base64
import json
import time
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os

class CardKeySystem:
    """卡密系统类"""
    
    # 银行标识映射（4位代码）
    BANK_IDS = {
        '中国银行': 'BOC0',
        '农业银行': 'ABC0',
        '建设银行': 'CCB0',
        '工商银行': 'ICBC',
        '邮政银行': 'PSBC'
    }
    
    def __init__(self, secret_key=None):
        """
        初始化卡密系统
        
        Args:
            secret_key: 加密密钥，如果为None则自动生成
        """
        if secret_key is None:
            secret_key = self._generate_secret_key()
        
        self.cipher = Fernet(secret_key)
    
    def _generate_secret_key(self):
        """生成加密密钥"""
        password = b"BankCardKeySystem2024!@#$%^&*()_+"
        salt = b"BankCardSalt2024!@#$%^&*()_+"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def generate_card_key(self, bank_name, days_valid=365):
        """
        生成卡密
        
        Args:
            bank_name: 银行名称（如：中国银行、农业银行等）
            days_valid: 有效天数，默认365天
        
        Returns:
            卡密字符串
        """
        if bank_name not in self.BANK_IDS:
            raise ValueError(f"不支持的银行: {bank_name}")
        
        bank_id = self.BANK_IDS[bank_name]
        
        # 生成简短的随机数据（8字节）
        random_data = secrets.token_hex(8)
        
        # 生成时间戳（简化为6位）
        timestamp = str(int(time.time()))[-6:]
        
        # 计算过期时间（简化为2位编码）
        expire_code = str(min(days_valid, 99)).zfill(2)
        
        # 构建简短卡密数据
        card_data = f"{bank_id}{timestamp}{expire_code}{random_data}"
        
        # 计算校验和（简化为4位）
        checksum = hashlib.md5(card_data.encode()).hexdigest()[:4]
        
        # 组合最终卡密
        card_key = f"{card_data}{checksum}"
        
        # 格式化卡密（每8位加一个横线）
        formatted_key = self._format_card_key(card_key)
        
        return formatted_key
    
    def verify_card_key(self, card_key, bank_name):
        """
        验证卡密
        
        Args:
            card_key: 卡密字符串
            bank_name: 银行名称
        
        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 去除格式化
            clean_key = card_key.replace('-', '').replace(' ', '')
            
            # 验证长度（银行ID 4位 + 时间戳 6位 + 过期码 2位 + 随机数 16位 + 校验和 4位 = 32位）
            if len(clean_key) != 32:
                return False, "卡密格式错误"
            
            # 提取各部分
            bank_id = clean_key[:4]
            timestamp = clean_key[4:10]
            expire_code = clean_key[10:12]
            random_data = clean_key[12:28]
            checksum = clean_key[28:32]
            
            # 验证银行标识
            if bank_name not in self.BANK_IDS:
                return False, f"不支持的银行: {bank_name}"
            
            expected_bank_id = self.BANK_IDS[bank_name]
            if bank_id != expected_bank_id:
                return False, f"卡密不适用于{bank_name}"
            
            # 验证校验和
            card_data = f"{bank_id}{timestamp}{expire_code}{random_data}"
            expected_checksum = hashlib.md5(card_data.encode()).hexdigest()[:4]
            if checksum != expected_checksum:
                return False, "卡密校验失败"
            
            return True, "卡密有效"
            
        except Exception as e:
            return False, f"卡密验证失败: {str(e)}"
    
    def _generate_signature(self, data):
        """生成签名"""
        signature = hashlib.sha256(data + b"BankCardSignature2024").digest()
        return signature
    
    def _verify_signature(self, data, signature):
        """验证签名"""
        expected_signature = self._generate_signature(data)
        return secrets.compare_digest(expected_signature, signature)
    
    def _format_card_key(self, card_key):
        """格式化卡密"""
        # 移除已有的横线
        clean_key = card_key.replace('-', '')
        
        # 每8位加一个横线
        parts = [clean_key[i:i+8] for i in range(0, len(clean_key), 8)]
        formatted = '-'.join(parts)
        
        return formatted


# 测试代码
if __name__ == '__main__':
    card_system = CardKeySystem()
    
    # 生成中国银行的卡密
    boc_key = card_system.generate_card_key('中国银行')
    print(f"中国银行卡密: {boc_key}")
    
    # 验证卡密
    is_valid, message = card_system.verify_card_key(boc_key, '中国银行')
    print(f"验证结果: {is_valid}, 消息: {message}")
    
    # 生成农业银行的卡密
    abc_key = card_system.generate_card_key('农业银行')
    print(f"农业银行卡密: {abc_key}")
    
    # 测试错误的银行
    is_valid, message = card_system.verify_card_key(boc_key, '农业银行')
    print(f"用中国银行卡密验证农业银行: {is_valid}, 消息: {message}")
