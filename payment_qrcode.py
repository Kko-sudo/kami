# -*- coding: utf-8 -*-
"""
支付二维码生成模块
用于生成支付宝和微信支付二维码
"""

import qrcode
import qrcode.constants
import io
import base64
from datetime import datetime
import hashlib
import secrets

class PaymentQRCodeGenerator:
    """支付二维码生成器"""
    
    def __init__(self, alipay_account='', wechat_account=''):
        """
        初始化支付二维码生成器
        
        Args:
            alipay_account: 支付宝账号
            wechat_account: 微信账号
        """
        self.alipay_account = alipay_account
        self.wechat_account = wechat_account
    
    def generate_alipay_qrcode(self, amount, order_id, description='银行卡密'):
        """
        生成支付宝支付二维码
        
        Args:
            amount: 支付金额
            order_id: 订单ID
            description: 商品描述
        
        Returns:
            (二维码图片base64, 二维码内容)
        """
        # 生成支付宝支付链接
        # 注意：这里使用的是模拟链接，实际使用时需要替换为真实的支付宝支付接口
        qr_content = f"alipays://platformapi/startapp?saId=10000007&qrcode=https://qr.alipay.com/{self.alipay_account}?amount={amount}&order_id={order_id}"
        
        # 生成二维码
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 转换为base64
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.getvalue()).decode()
        
        return img_base64, qr_content
    
    def generate_wechat_qrcode(self, amount, order_id, description='银行卡密'):
        """
        生成微信支付二维码
        
        Args:
            amount: 支付金额
            order_id: 订单ID
            description: 商品描述
        
        Returns:
            (二维码图片base64, 二维码内容)
        """
        # 生成微信支付链接
        # 注意：这里使用的是模拟链接，实际使用时需要替换为真实的微信支付接口
        qr_content = f"weixin://wxpay/bizpayurl?pr={self.wechat_account}&amount={amount}&order_id={order_id}"
        
        # 生成二维码
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 转换为base64
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.getvalue()).decode()
        
        return img_base64, qr_content
    
    def generate_payment_qrcode(self, payment_method, amount, order_id, description='银行卡密'):
        """
        生成支付二维码（统一接口）
        
        Args:
            payment_method: 支付方式 ('alipay' 或 'wechat')
            amount: 支付金额
            order_id: 订单ID
            description: 商品描述
        
        Returns:
            (二维码图片base64, 二维码内容)
        """
        if payment_method == 'alipay':
            return self.generate_alipay_qrcode(amount, order_id, description)
        elif payment_method == 'wechat':
            return self.generate_wechat_qrcode(amount, order_id, description)
        else:
            raise ValueError(f"不支持的支付方式: {payment_method}")
    
    def generate_transaction_id(self, order_id):
        """
        生成交易ID
        
        Args:
            order_id: 订单ID
        
        Returns:
            交易ID
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_str = secrets.token_hex(4)
        transaction_id = f"{order_id}{timestamp}{random_str}"
        return transaction_id


# 测试代码
if __name__ == '__main__':
    # 测试二维码生成
    qr_generator = PaymentQRCodeGenerator(
        alipay_account='your_alipay_account',
        wechat_account='your_wechat_account'
    )
    
    # 生成支付宝二维码
    alipay_qr, alipay_content = qr_generator.generate_alipay_qrcode(
        amount=79.90,
        order_id=12345,
        description='中国银行卡密'
    )
    
    print(f"支付宝二维码长度: {len(alipay_qr)}")
    print(f"支付宝二维码内容: {alipay_content}")
    
    # 生成微信二维码
    wechat_qr, wechat_content = qr_generator.generate_wechat_qrcode(
        amount=79.90,
        order_id=12345,
        description='中国银行卡密'
    )
    
    print(f"微信二维码长度: {len(wechat_qr)}")
    print(f"微信二维码内容: {wechat_content}")
    
    # 生成交易ID
    transaction_id = qr_generator.generate_transaction_id(12345)
    print(f"交易ID: {transaction_id}")
