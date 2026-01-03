# -*- coding: utf-8 -*-
"""
邮件发送模块
用于发送卡密到用户邮箱
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailSender:
    """邮件发送器"""
    
    def __init__(self, smtp_server='smtp.qq.com', smtp_port=587, 
                 smtp_username='', smtp_password=''):
        """
        初始化邮件发送器
        
        Args:
            smtp_server: SMTP服务器地址
            smtp_port: SMTP端口
            smtp_username: SMTP用户名（邮箱地址）
            smtp_password: SMTP密码（授权码）
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
    
    def send_card_key_email(self, to_email, bank_name, card_key, days_valid):
        """
        发送卡密邮件
        
        Args:
            to_email: 收件人邮箱
            bank_name: 银行名称
            card_key: 卡密
            days_valid: 有效天数
        
        Returns:
            (是否成功, 错误信息)
        """
        try:
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = to_email
            msg['Subject'] = f'您的{bank_name}卡密已生成'
            
            # 邮件正文
            body = f'''
尊敬的用户：

您好！您的{bank_name}卡密已成功生成。

卡密信息：
- 银行：{bank_name}
- 卡密：{card_key}
- 有效期：{days_valid}天

请妥善保管您的卡密，如有任何问题，请联系客服。

此邮件由系统自动发送，请勿回复。

祝您使用愉快！
'''
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # 连接SMTP服务器并发送邮件
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"邮件发送成功: {to_email}")
            return True, "邮件发送成功"
            
        except Exception as e:
            logger.error(f"邮件发送失败: {str(e)}")
            return False, str(e)
    
    def send_order_confirmation_email(self, to_email, order_id, bank_name, card_type, price):
        """
        发送订单确认邮件
        
        Args:
            to_email: 收件人邮箱
            order_id: 订单ID
            bank_name: 银行名称
            card_type: 卡密类型
            price: 价格
        
        Returns:
            (是否成功, 错误信息)
        """
        try:
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = to_email
            msg['Subject'] = f'订单确认 - 订单号: {order_id}'
            
            # 邮件正文
            body = f'''
尊敬的用户：

您好！您的订单已成功创建。

订单信息：
- 订单号：{order_id}
- 银行：{bank_name}
- 卡密类型：{card_type}
- 价格：¥{price:.2f}

请完成支付后，卡密将自动发送到您的邮箱。

此邮件由系统自动发送，请勿回复。

祝您使用愉快！
'''
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # 连接SMTP服务器并发送邮件
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"订单确认邮件发送成功: {to_email}")
            return True, "邮件发送成功"
            
        except Exception as e:
            logger.error(f"订单确认邮件发送失败: {str(e)}")
            return False, str(e)


# 测试代码
if __name__ == '__main__':
    # 测试邮件发送（需要配置真实的SMTP信息）
    email_sender = EmailSender(
        smtp_server='smtp.qq.com',
        smtp_port=587,
        smtp_username='your_email@qq.com',
        smtp_password='your_authorization_code'
    )
    
    # 测试发送卡密邮件
    success, message = email_sender.send_card_key_email(
        to_email='test@example.com',
        bank_name='中国银行',
        card_key='BOC01234-5678abcd-efghijkl-mnopqrst',
        days_valid=30
    )
    
    print(f"发送结果: {success}, 消息: {message}")
