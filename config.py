# -*- coding: utf-8 -*-
"""
系统配置文件
用于存储SMTP和支付账号信息
"""

import os

class Config:
    """系统配置类"""
    
    # SMTP配置（用于发送邮件）
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.qq.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')  # 发件人邮箱
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')  # 邮箱授权码（不是登录密码）
    
    # 支付宝配置
    ALIPAY_ACCOUNT = os.getenv('ALIPAY_ACCOUNT', '')  # 支付宝账号或收款码
    
    # 微信支付配置
    WECHAT_ACCOUNT = os.getenv('WECHAT_ACCOUNT', '')  # 微信支付账号或收款码
    
    # 系统配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # 数据库配置
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'bank_card_system.db')
    
    # 服务器配置
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    
    @classmethod
    def validate_config(cls):
        """验证配置是否完整"""
        errors = []
        
        if not cls.SMTP_USERNAME:
            errors.append('SMTP_USERNAME未配置，邮件发送功能将不可用')
        
        if not cls.SMTP_PASSWORD:
            errors.append('SMTP_PASSWORD未配置，邮件发送功能将不可用')
        
        if not cls.ALIPAY_ACCOUNT:
            errors.append('ALIPAY_ACCOUNT未配置，支付宝支付功能将不可用')
        
        if not cls.WECHAT_ACCOUNT:
            errors.append('WECHAT_ACCOUNT未配置，微信支付功能将不可用')
        
        return errors


# 使用示例：
# 1. 创建.env文件，添加以下内容：
#    SMTP_SERVER=smtp.qq.com
#    SMTP_PORT=587
#    SMTP_USERNAME=your_email@qq.com
#    SMTP_PASSWORD=your_authorization_code
#    ALIPAY_ACCOUNT=your_alipay_account
#    WECHAT_ACCOUNT=your_wechat_account
#    SECRET_KEY=your-secret-key
#    DEBUG=True
#    DATABASE_PATH=bank_card_system.db
#    HOST=0.0.0.0
#    PORT=5000
#
# 2. 在代码中使用：
#    from config import Config
#    print(Config.SMTP_USERNAME)
#    print(Config.ALIPAY_ACCOUNT)
#
# 3. 验证配置：
#    from config import Config
#    errors = Config.validate_config()
#    if errors:
#        print("配置错误：")
#        for error in errors:
#            print(f"  - {error}")
#    else:
#        print("配置完整")
