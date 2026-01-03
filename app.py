from flask import Flask, request, jsonify, session, render_template, redirect, send_from_directory
from functools import wraps
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import hashlib
import os
import uuid
import logging
from dotenv import load_dotenv

load_dotenv()

from database import Database
from card_key_system import CardKeySystem
from email_sender import EmailSender
from payment_qrcode import PaymentQRCodeGenerator
from payment_status_checker import PaymentStatusChecker
from config import Config
from ympay import YmPayConfig

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# 启用CSRF保护
csrf = CSRFProtect(app)

# 配置速率限制
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Session配置
app.config['SESSION_COOKIE_SECURE'] = False  # 开发环境设为False，生产环境设为True（HTTPS）
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 同站点请求
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24小时
app.config['SESSION_COOKIE_NAME'] = 'session'  # 明确设置 cookie 名称
app.config['SESSION_REFRESH_EACH_REQUEST'] = False  # 不每次请求都刷新 session

# 初始化数据库（必须成功）
try:
    db = Database()
    logger.info("数据库初始化成功")
except Exception as e:
    logger.error(f"数据库初始化失败: {str(e)}")
    logger.error("应用无法启动，数据库是必需的")
    raise

# 初始化卡密系统（必须成功）
try:
    card_system = CardKeySystem()
    logger.info("卡密系统初始化成功")
except Exception as e:
    logger.error(f"卡密系统初始化失败: {str(e)}")
    logger.error("应用无法启动，卡密系统是必需的")
    raise

# 初始化邮件发送器（可选，失败不影响启动）
email_sender = None
try:
    email_sender = EmailSender(
        smtp_server=Config.SMTP_SERVER,
        smtp_port=Config.SMTP_PORT,
        smtp_username=Config.SMTP_USERNAME,
        smtp_password=Config.SMTP_PASSWORD
    )
    logger.info("邮件发送器初始化成功")
except Exception as e:
    logger.warning(f"邮件发送器初始化失败: {str(e)}")
    logger.warning("邮件发送功能将不可用")

# 初始化支付二维码生成器（可选，失败不影响启动）
qr_generator = None
try:
    qr_generator = PaymentQRCodeGenerator(
        alipay_account=Config.ALIPAY_ACCOUNT,
        wechat_account=Config.WECHAT_ACCOUNT
    )
    logger.info("支付二维码生成器初始化成功")
except Exception as e:
    logger.warning(f"支付二维码生成器初始化失败: {str(e)}")
    logger.warning("支付二维码生成功能将不可用")

# 初始化支付状态检测器（可选，失败不影响启动）
payment_checker = None
try:
    payment_checker = PaymentStatusChecker(db)
    logger.info("支付状态检测器初始化成功")
except Exception as e:
    logger.warning(f"支付状态检测器初始化失败: {str(e)}")
    logger.warning("支付状态检测功能将不可用")

# 初始化YmPay配置（可选，失败不影响启动）
ympay_config = None
try:
    ympay_config = YmPayConfig()
    logger.info("YmPay配置初始化成功")
except Exception as e:
    logger.warning(f"YmPay配置初始化失败: {str(e)}")
    logger.warning("YmPay功能将不可用")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            else:
                return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        if not session.get('admin_is_admin'):
            return jsonify({'success': False, 'message': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': '请求的资源不存在'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"服务器内部错误: {str(error)}")
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': '服务器内部错误，请稍后重试'}), 500
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': '访问被拒绝'}), 403
    return render_template('403.html'), 403

@app.errorhandler(401)
def unauthorized(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': '未授权访问'}), 401
    return redirect('/login')

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"未处理的异常: {str(e)}", exc_info=True)
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': '服务器错误，请稍后重试'}), 500
    return render_template('500.html'), 500

@app.route('/api/register', methods=['POST'], endpoint='api_register')
@limiter.limit("5 per hour")
def register():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        
        # 输入验证
        if not username or not password:
            return jsonify({'success': False, 'message': '用户名和密码不能为空'})
        
        # 用户名长度和格式验证
        if len(username) < 3 or len(username) > 20:
            return jsonify({'success': False, 'message': '用户名长度必须在3-20位之间'})
        
        if not username.isalnum():
            return jsonify({'success': False, 'message': '用户名只能包含字母和数字'})
        
        # 密码长度验证
        if len(password) < 6 or len(password) > 50:
            return jsonify({'success': False, 'message': '密码长度必须在6-50位之间'})
        
        # 邮箱格式验证
        if email and '@' not in email:
            return jsonify({'success': False, 'message': '邮箱格式不正确'})
        
        # 手机号格式验证
        if phone and not phone.isdigit():
            return jsonify({'success': False, 'message': '手机号只能包含数字'})
        
        success, message = db.create_user(username, password, email, phone)
        
        if success:
            logger.info(f"新用户注册成功: {username}")
            return jsonify({'success': True, 'message': '注册成功'})
        else:
            if '已存在' in message:
                return jsonify({'success': False, 'message': '该用户名已存在'})
            return jsonify({'success': False, 'message': message})
    except Exception as e:
        logger.error(f"注册失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': '注册失败，请稍后重试'})

@app.route('/api/login', methods=['POST'])
@limiter.limit("10 per hour")
def login():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        login_type = data.get('login_type', 'user')
        
        # 输入验证
        if not username or not password:
            return jsonify({'success': False, 'message': '用户名和密码不能为空'})
        
        # 验证登录类型
        if login_type not in ['user', 'admin']:
            return jsonify({'success': False, 'message': '无效的登录类型'})
        
        success, user = db.verify_user(username, password)
        
        if success:
            # 检查登录类型是否匹配
            if login_type == 'user' and user['is_admin']:
                return jsonify({'success': False, 'message': '请使用管理员登录页面'})
            
            if login_type == 'admin' and not user['is_admin']:
                return jsonify({'success': False, 'message': '需要管理员权限'})
            
            # 根据登录类型使用不同的session key
            if login_type == 'admin':
                session['admin_user_id'] = user['id']
                session['admin_username'] = user['username']
                session['admin_is_admin'] = user['is_admin']
                session.permanent = True
            else:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = user['is_admin']
                session.permanent = True
            
            # 检查是否首次登录
            first_login = user.get('first_login', 1)
            
            logger.info(f"用户登录成功: {username}, 类型: {login_type}")
            return jsonify({
                'success': True, 
                'message': '登录成功',
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'email': user['email'],
                    'phone': user['phone'],
                    'is_admin': user['is_admin'],
                    'first_login': first_login
                }
            })
        else:
            logger.warning(f"登录失败: {username}")
            return jsonify({'success': False, 'message': '用户名或密码错误'})
    except Exception as e:
        logger.error(f"登录异常: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': '登录失败，请稍后重试'})

@app.route('/api/logout', methods=['POST'])
def logout():
    login_type = request.json.get('login_type', 'user')
    
    if login_type == 'admin':
        # 只清除管理员session
        session.pop('admin_user_id', None)
        session.pop('admin_username', None)
        session.pop('admin_is_admin', None)
    else:
        # 只清除用户session
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('is_admin', None)
    
    return jsonify({'success': True, 'message': '退出成功'})

@app.route('/api/user/first-login', methods=['POST'])
@login_required
def mark_first_login_complete():
    """标记用户首次登录已完成"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET first_login = 0 WHERE id = ?', (session['user_id'],))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '首次登录标记已完成'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'操作失败: {str(e)}'})

@app.route('/api/user', methods=['GET'])
@login_required
def get_user():
    return jsonify({
        'username': session['username']
    })

@app.route('/api/user/info', methods=['GET'])
@login_required
def get_user_info():
    return jsonify({
        'success': True,
        'user': {
            'id': session['user_id'],
            'username': session['username'],
            'is_admin': session['is_admin']
        }
    })

@app.route('/api/user/verify', methods=['GET'])
@login_required
def verify_user_session():
    return jsonify({
        'success': True,
        'user': {
            'id': session['user_id'],
            'username': session['username'],
            'is_admin': session['is_admin']
        }
    })

@app.route('/api/card-keys/available', methods=['GET'])
def get_available_card_keys():
    card_keys = db.get_available_card_keys()
    return jsonify({
        'success': True,
        'card_keys': card_keys
    })

@app.route('/api/card-keys/purchase', methods=['POST'])
@login_required
def purchase_card_key():
    data = request.json
    card_key_id = data.get('card_key_id')
    contact_info = data.get('contact_info', '')
    
    if not card_key_id:
        return jsonify({'success': False, 'message': '请选择要购买的卡密'})
    
    success, message = db.purchase_card_key(session['user_id'], card_key_id, contact_info)
    
    if success:
        return jsonify({'success': True, 'message': '购买成功'})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/api/user/orders', methods=['GET'])
@login_required
def get_user_orders():
    orders = db.get_user_orders(session['user_id'])
    return jsonify({
        'success': True,
        'orders': orders
    })

@app.route('/api/orders', methods=['GET'])
@login_required
def get_orders():
    orders = db.get_user_orders(session['user_id'])
    return jsonify({
        'success': True,
        'orders': orders
    })

@app.route('/api/user/emails', methods=['GET'])
@login_required
def get_user_emails():
    emails = db.get_user_emails(session['user_id'])
    formatted_emails = []
    for email in emails:
        formatted_emails.append({
            'id': email['id'],
            'subject': email['subject'],
            'body': email['content'],
            'recipient': email.get('sender_username', '系统'),
            'created_at': email['created_at'],
            'is_read': email['is_read']
        })
    return jsonify({
        'success': True,
        'emails': formatted_emails
    })

@app.route('/api/emails', methods=['GET'])
@login_required
def get_emails():
    emails = db.get_user_emails_list(session['user_id'])
    formatted_emails = []
    for email in emails:
        formatted_emails.append({
            'id': email['id'],
            'email': email['email'],
            'created_at': email['created_at'],
            'status': email['status']
        })
    return jsonify({
        'success': True,
        'emails': formatted_emails
    })

@app.route('/api/emails', methods=['POST'])
@login_required
def add_email():
    data = request.json
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'message': '邮箱地址不能为空'})
    
    try:
        db.add_user_email(session['user_id'], email)
        return jsonify({'success': True, 'message': '邮箱添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': '添加失败，请重试'})

@app.route('/api/admin/generate-card-key', methods=['POST'])
@admin_required
def generate_card_key():
    data = request.json
    bank_name = data.get('bank_name')
    card_type = data.get('card_type', 'standard')
    
    if not bank_name:
        return jsonify({'success': False, 'message': '请选择银行'})
    
    try:
        success, result = db.generate_card_key(bank_name, card_type)
        
        if success:
            return jsonify({
                'success': True, 
                'message': '卡密生成成功',
                'card_key': result['card_key']
            })
        else:
            return jsonify({'success': False, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成失败: {str(e)}'})

@app.route('/api/admin/card-keys', methods=['GET'])
@admin_required
def get_all_card_keys():
    card_keys = db.get_all_card_keys()
    return jsonify({
        'success': True,
        'card_keys': card_keys
    })

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    users = db.get_all_users()
    return jsonify({
        'success': True,
        'users': users
    })

@app.route('/api/admin/orders', methods=['GET'])
@admin_required
def get_all_orders():
    orders = db.get_all_orders()
    return jsonify({
        'success': True,
        'orders': orders
    })

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_stats():
    stats = db.get_stats()
    return jsonify({
        'success': True,
        'stats': stats
    })

@app.route('/api/admin/card-key/<int:card_key_id>', methods=['DELETE'])
@admin_required
def delete_card_key(card_key_id):
    success, message = db.delete_card_key(card_key_id)
    
    if success:
        return jsonify({'success': True, 'message': '删除成功'})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/api/emails/send', methods=['POST'])
@admin_required
def send_email():
    data = request.json
    user_id = data.get('user_id')
    subject = data.get('subject')
    content = data.get('content')
    
    if not user_id or not subject or not content:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    sender_id = session.get('admin_user_id')
    success, result = db.send_email(user_id, sender_id, subject, content)
    
    if success:
        return jsonify({'success': True, 'message': '邮件发送成功'})
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/api/emails/<int:email_id>/read', methods=['POST'])
@login_required
def mark_email_as_read(email_id):
    success, message = db.mark_email_as_read(email_id, session['user_id'])
    
    if success:
        return jsonify({'success': True, 'message': '标记成功'})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/api/admin/emails', methods=['GET'])
@admin_required
def get_all_emails():
    emails = db.get_all_emails()
    return jsonify({
        'success': True,
        'emails': emails
    })

@app.route('/api/admin/send-card-key', methods=['POST'])
@admin_required
def send_card_key_to_user():
    data = request.json
    user_id = data.get('user_id')
    card_key = data.get('card_key')
    bank_name = data.get('bank_name')
    
    if not user_id or not card_key:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'})
    
    subject = f"您的卡密已到账 - {bank_name}"
    content = f"尊敬的用户 {user['username']}：\n\n您的卡密已到账，请查收：\n\n银行：{bank_name}\n卡密：{card_key}\n\n请注意保管好您的卡密，如有问题请联系客服。"
    
    sender_id = session.get('admin_user_id')
    success, result = db.send_email(user_id, sender_id, subject, content)
    
    if success:
        return jsonify({'success': True, 'message': '卡密发送成功'})
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/api/admin/order/generate-card-key', methods=['POST'])
@admin_required
def generate_card_key_for_order():
    try:
        data = request.json
        order_id = data.get('order_id')
        
        if not order_id:
            return jsonify({'success': False, 'message': '订单ID不能为空'})
        
        success, result = db.generate_card_key_for_order(order_id)
        
        if success:
            logger.info(f"管理员为订单生成卡密成功: order_id={order_id}")
            return jsonify({
                'success': True,
                'message': '卡密生成成功',
                'card_key': result['card_key']
            })
        else:
            logger.warning(f"管理员为订单生成卡密失败: order_id={order_id}, reason={result}")
            return jsonify({'success': False, 'message': result})
    except Exception as e:
        logger.error(f"管理员为订单生成卡密异常: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': '生成失败，请稍后重试'})

@app.route('/api/admin/order/send-card-key', methods=['POST'])
@admin_required
def send_card_key_for_order():
    data = request.json
    order_id = data.get('order_id')
    
    if not order_id:
        return jsonify({'success': False, 'message': '订单ID不能为空'})
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 获取订单信息
        cursor.execute('''
            SELECT o.id, o.user_id, o.card_key_id, o.bank_name, o.status,
                   c.card_key
            FROM orders o
            LEFT JOIN card_keys c ON o.card_key_id = c.id
            WHERE o.id = ?
        ''', (order_id,))
        
        order = cursor.fetchone()
        conn.close()
        
        if not order:
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if not order['card_key']:
            return jsonify({'success': False, 'message': '该订单尚未生成卡密，请先生成卡密'})
        
        user = db.get_user_by_id(order['user_id'])
        if not user:
            return jsonify({'success': False, 'message': '用户不存在'})
        
        subject = f"您的卡密已到账 - {order['bank_name']}"
        content = f"尊敬的用户 {user['username']}：\n\n您的卡密已到账，请查收：\n\n银行：{order['bank_name']}\n卡密：{order['card_key']}\n\n请注意保管好您的卡密，如有问题请联系客服。"
        
        sender_id = session.get('admin_user_id')
        success, result = db.send_email(order['user_id'], sender_id, subject, content)
        
        if success:
            # 更新订单状态为已完成
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE orders SET status = ?, paid_at = datetime("now") WHERE id = ?', ('completed', order_id))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': '卡密发送成功'})
        else:
            return jsonify({'success': False, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'message': f'发送失败: {str(e)}'})

@app.route('/api/admin/user/<int:user_id>', methods=['GET'])
@admin_required
def get_user_by_id(user_id):
    user = db.get_user_by_id(user_id)
    
    if user:
        return jsonify({'success': True, 'user': user})
    else:
        return jsonify({'success': False, 'message': '用户不存在'})

@app.route('/api/banks', methods=['GET'])
def get_banks():
    banks = [
        {'id': 'BOC', 'name': '中国银行'},
        {'id': 'ABC', 'name': '农业银行'},
        {'id': 'CCB', 'name': '建设银行'},
        {'id': 'ICBC', 'name': '工商银行'},
        {'id': 'PSBC', 'name': '邮政银行'}
    ]
    return jsonify({
        'success': True,
        'banks': banks
    })

@app.route('/api/banks/available', methods=['GET'])
def get_available_banks():
    banks = [
        '中国银行',
        '农业银行',
        '建设银行',
        '工商银行',
        '邮政银行'
    ]
    return jsonify({
        'success': True,
        'banks': banks
    })

@app.route('/api/orders/create', methods=['POST'])
@login_required
def create_order():
    try:
        data = request.json
        banks = data.get('banks', [])
        card_type = data.get('card_type')
        quantities = data.get('quantities', [])
        
        if not banks or len(banks) == 0:
            return jsonify({'success': False, 'message': '请至少选择一个银行'})
        
        if not card_type:
            return jsonify({'success': False, 'message': '请选择卡密类型'})
        
        # 检查1天卡密限购
        if card_type == '1day':
            user_id = session.get('user_id')
            ip_address = request.remote_addr
            device_fingerprint = request.headers.get('User-Agent', '')
            
            has_purchased, purchase_info = db.check_1day_card_purchase(user_id, ip_address, device_fingerprint)
            if has_purchased:
                if purchase_info.get('reason') == 'user':
                    return jsonify({'success': False, 'message': '1天体验卡每个账号只能购买一次，您已经购买过了'})
                else:
                    return jsonify({'success': False, 'message': '1天体验卡每个设备只能购买一次，该设备已经购买过了'})
        
        user_id = session.get('user_id')
        success, result = db.create_order(user_id, banks, card_type, '', quantities)
        
        if success:
            order_id = result['order_id']
            total_price = result['total_price']
            total_items = result['total_items']
            
            # 记录1天卡密购买信息
            if card_type == '1day':
                ip_address = request.remote_addr
                device_fingerprint = request.headers.get('User-Agent', '')
                db.record_1day_card_purchase(user_id, ip_address, device_fingerprint)
            
            # 创建支付记录
            payment_success, payment_result = db.create_payment(
                order_id=order_id,
                payment_method='alipay_wechat',
                amount=total_price,
                qr_code='/static/images/payment_qrcode.png'
            )
            
            if not payment_success:
                logger.error(f"支付记录创建失败: {payment_result}")
                return jsonify({'success': False, 'message': '支付记录创建失败，请稍后重试'})
            
            logger.info(f"订单创建成功: order_id={order_id}, user_id={user_id}, total_price={total_price}")
            return jsonify({
                'success': True,
                'message': '订单创建成功，请完成支付',
                'order_id': order_id,
                'total_price': total_price,
                'total_items': total_items
            })
        else:
            logger.warning(f"订单创建失败: {result}")
            return jsonify({'success': False, 'message': result})
    except Exception as e:
        logger.error(f"订单创建异常: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': '订单创建失败，请稍后重试'})

@app.route('/api/orders/<int:order_id>/status', methods=['GET'])
@login_required
def get_order_status(order_id):
    try:
        user_id = session.get('user_id')
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, bank_name, card_type, days_valid, card_key, price, status, created_at, paid_at, order_group_id
            FROM orders WHERE id = ? AND user_id = ?
        ''', (order_id, user_id))
        order = cursor.fetchone()
        conn.close()
        
        if order:
            order_dict = {
                'id': order[0],
                'user_id': order[1],
                'bank_name': order[2],
                'card_type': order[3],
                'days_valid': order[4],
                'card_key': order[5],
                'price': order[6],
                'status': order[7],
                'created_at': order[8],
                'paid_at': order[9],
                'order_group_id': order[10]
            }
            return jsonify({'success': True, 'order': order_dict})
        else:
            return jsonify({'success': False, 'message': '订单不存在'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取订单状态失败: {str(e)}'})

@app.route('/api/order-groups/<int:order_group_id>/status', methods=['GET'])
@login_required
def get_order_group_status(order_group_id):
    try:
        user_id = session.get('user_id')
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, total_price, total_items, card_type, status, created_at, paid_at
            FROM order_groups WHERE id = ? AND user_id = ?
        ''', (order_group_id, user_id))
        order_group = cursor.fetchone()
        conn.close()
        
        if order_group:
            order_group_dict = {
                'id': order_group[0],
                'user_id': order_group[1],
                'total_price': order_group[2],
                'total_items': order_group[3],
                'card_type': order_group[4],
                'status': order_group[5],
                'created_at': order_group[6],
                'paid_at': order_group[7],
                'order_group_id': order_group[0]
            }
            return jsonify({'success': True, 'order': order_group_dict})
        else:
            return jsonify({'success': False, 'message': '订单组不存在'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取订单组状态失败: {str(e)}'})

@app.route('/api/orders/<int:order_id>/confirm-payment', methods=['POST'])
@login_required
def confirm_payment(order_id):
    try:
        user_id = session.get('user_id')
        
        # 获取订单信息
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE id = ? AND user_id = ?', (order_id, user_id))
        order = cursor.fetchone()
        
        if not order:
            conn.close()
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if order['status'] == 'completed':
            conn.close()
            return jsonify({'success': False, 'message': '订单已完成'})
        
        # 检查订单是否超时（15分钟）
        from datetime import datetime, timedelta
        created_at = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() - created_at > timedelta(minutes=15):
            conn.close()
            return jsonify({'success': False, 'message': '订单已超时，请重新下单'})
        
        # 检查支付状态
        payment = db.get_payment_by_order(order_id)
        if not payment:
            conn.close()
            return jsonify({'success': False, 'message': '支付记录不存在，请先完成支付'})
        
        if payment['status'] != 'completed':
            conn.close()
            return jsonify({'success': False, 'message': '支付尚未完成，请先完成支付'})
        
        # 检查是否已经生成过卡密
        if order['card_key']:
            conn.close()
            return jsonify({'success': False, 'message': '卡密已生成'})
        
        # 生成卡密
        gen_success, gen_result = db.generate_card_key_for_order(order_id)
        if not gen_success:
            conn.close()
            return jsonify({'success': False, 'message': f'卡密生成失败: {gen_result}'})
        
        # 获取用户信息并发送邮件
        cursor.execute('SELECT email FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user and user['email']:
            send_success, send_msg = email_sender.send_card_key_email(
                to_email=user['email'],
                bank_name=order['bank_name'],
                card_key=gen_result['card_key'],
                days_valid=gen_result['days_valid']
            )
            
            if send_success:
                # 更新订单状态为已完成
                cursor.execute('UPDATE orders SET status = ?, paid_at = datetime("now") WHERE id = ?', ('completed', order_id))
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'message': '支付确认成功，卡密已发送到您的邮箱'
                })
            else:
                conn.close()
                return jsonify({
                    'success': False,
                    'message': f'卡密已生成，但邮件发送失败: {send_msg}'
                })
        else:
            # 没有邮箱，只更新订单状态
            cursor.execute('UPDATE orders SET status = ?, paid_at = datetime("now") WHERE id = ?', ('completed', order_id))
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': '支付确认成功，请完善邮箱信息以便接收卡密'
            })
    except Exception as e:
        return jsonify({'success': False, 'message': f'确认支付失败: {str(e)}'})

@app.route('/api/admin/orders/<int:order_id>/cancel', methods=['POST'])
@admin_required
def admin_cancel_order(order_id):
    """管理员取消订单"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 检查订单是否存在
        cursor.execute('SELECT id, status FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            conn.close()
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if order['status'] in ['paid', 'completed']:
            conn.close()
            return jsonify({'success': False, 'message': '已支付或已完成的订单无法取消'})
        
        # 更新订单状态为已取消
        cursor.execute('UPDATE orders SET status = ? WHERE id = ?', ('cancelled', order_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '订单已取消'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'取消订单失败: {str(e)}'})

@app.route('/api/orders/<int:order_id>/user-confirm', methods=['POST'])
@login_required
def user_confirm_payment(order_id):
    """用户确认已支付，等待管理员审核"""
    try:
        user_id = session.get('user_id')
        
        # 获取订单信息
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE id = ? AND user_id = ?', (order_id, user_id))
        order = cursor.fetchone()
        
        if not order:
            conn.close()
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if order['status'] == 'completed':
            conn.close()
            return jsonify({'success': False, 'message': '订单已完成'})
        
        if order['status'] == 'awaiting_confirmation':
            conn.close()
            return jsonify({'success': False, 'message': '订单已提交，请等待管理员确认'})
        
        if order['status'] == 'paid':
            conn.close()
            return jsonify({'success': False, 'message': '订单已支付，请查看卡密'})
        
        # 检查订单是否超时（15分钟）
        from datetime import datetime, timedelta
        created_at = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() - created_at > timedelta(minutes=15):
            conn.close()
            return jsonify({'success': False, 'message': '订单已超时，请重新下单'})
        
        # 更新订单状态为待确认
        cursor.execute('UPDATE orders SET status = ? WHERE id = ?', ('awaiting_confirmation', order_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '已提交支付确认，请等待管理员审核'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'提交失败: {str(e)}'})

@app.route('/api/order-groups/<int:order_group_id>/user-confirm', methods=['POST'])
@login_required
def user_confirm_payment_group(order_group_id):
    """用户确认订单组已支付，等待管理员审核"""
    try:
        user_id = session.get('user_id')
        logger.info(f"用户确认支付 - order_group_id: {order_group_id}, user_id: {user_id}")
        
        # 获取订单组信息
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM order_groups WHERE id = ? AND user_id = ?', (order_group_id, user_id))
        order_group = cursor.fetchone()
        
        if not order_group:
            conn.close()
            logger.warning(f"订单组不存在 - order_group_id: {order_group_id}, user_id: {user_id}")
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if order_group['status'] == 'completed':
            conn.close()
            return jsonify({'success': False, 'message': '订单已完成'})
        
        if order_group['status'] == 'awaiting_confirmation':
            conn.close()
            return jsonify({'success': False, 'message': '订单已提交，请等待管理员确认'})
        
        if order_group['status'] == 'paid':
            conn.close()
            return jsonify({'success': False, 'message': '订单已支付，请查看卡密'})
        
        # 检查订单组是否超时（15分钟）
        from datetime import datetime, timedelta
        created_at = datetime.strptime(order_group['created_at'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() - created_at > timedelta(minutes=15):
            conn.close()
            return jsonify({'success': False, 'message': '订单已超时，请重新下单'})
        
        # 更新订单组状态为待确认
        cursor.execute('UPDATE order_groups SET status = ? WHERE id = ?', ('awaiting_confirmation', order_group_id))
        
        # 更新所有关联订单的状态为待确认
        cursor.execute('UPDATE orders SET status = ? WHERE order_group_id = ?', ('awaiting_confirmation', order_group_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '已提交支付确认，请等待管理员审核'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'提交失败: {str(e)}'})

@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    """取消订单"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 检查订单是否存在
        cursor.execute('SELECT id, user_id, status FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            conn.close()
            return jsonify({'success': False, 'message': '订单不存在'})
        
        # 检查订单是否属于当前用户
        if order['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': '无权操作此订单'})
        
        # 检查订单状态
        if order['status'] in ['paid', 'completed']:
            conn.close()
            return jsonify({'success': False, 'message': '已支付或已完成的订单无法取消'})
        
        # 删除订单
        cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '订单已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'取消订单失败: {str(e)}'})

@app.route('/api/order-groups/<int:order_group_id>/cancel', methods=['POST'])
@login_required
def cancel_order_group(order_group_id):
    """取消订单组"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 检查订单组是否存在
        cursor.execute('SELECT id, user_id, status FROM order_groups WHERE id = ?', (order_group_id,))
        order_group = cursor.fetchone()
        
        if not order_group:
            conn.close()
            return jsonify({'success': False, 'message': '订单不存在'})
        
        # 检查订单组是否属于当前用户
        if order_group['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': '无权操作此订单'})
        
        # 检查订单组状态
        if order_group['status'] in ['paid', 'completed']:
            conn.close()
            return jsonify({'success': False, 'message': '已支付或已完成的订单无法取消'})
        
        # 删除订单组下的所有订单
        cursor.execute('DELETE FROM orders WHERE order_group_id = ?', (order_group_id,))
        
        # 删除订单组
        cursor.execute('DELETE FROM order_groups WHERE id = ?', (order_group_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': '订单已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'取消订单失败: {str(e)}'})

@app.route('/api/admin/orders/<int:order_id>/confirm-payment', methods=['POST'])
@admin_required
def admin_confirm_payment(order_id):
    """管理员手动确认支付"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 检查订单是否存在
        cursor.execute('SELECT id, user_id, status, card_key_id FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            conn.close()
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if order['status'] in ['paid', 'completed']:
            conn.close()
            return jsonify({'success': False, 'message': '订单已经支付或完成'})
        
        # 更新订单状态为已支付（支持从pending和awaiting_confirmation状态确认）
        cursor.execute('UPDATE orders SET status = ?, paid_at = datetime("now") WHERE id = ?', ('paid', order_id))
        conn.commit()
        conn.close()
        
        # 生成卡密（在关闭连接后再生成，避免数据库锁定）
        gen_success, gen_result = db.generate_card_key_for_order(order_id)
        
        if gen_success:
            # 重新获取连接来更新订单和发送邮件
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # 获取用户邮箱
            cursor.execute('SELECT email FROM users WHERE id = ?', (order['user_id'],))
            user = cursor.fetchone()
            
            if user and user['email']:
                # 发送卡密到邮箱
                cursor.execute('SELECT c.card_key, o.bank_name FROM card_keys c JOIN orders o ON c.id = o.card_key_id WHERE o.id = ?', (order_id,))
                card_info = cursor.fetchone()
                
                if card_info:
                    subject = f"您的卡密已到账 - {card_info['bank_name']}"
                    content = f"尊敬的用户：\n\n您的卡密已到账，请查收：\n\n银行：{card_info['bank_name']}\n卡密：{card_info['card_key']}\n\n请注意保管好您的卡密，如有问题请联系客服。"
                    
                    sender_id = session.get('user_id')
                    send_success, send_msg = db.send_email(order['user_id'], sender_id, subject, content)
                    
                    if send_success:
                        # 更新订单状态为已完成
                        cursor.execute('UPDATE orders SET status = ? WHERE id = ?', ('completed', order_id))
                        conn.commit()
                        conn.close()
                        return jsonify({'success': True, 'message': '支付确认成功，卡密已发送到用户邮箱'})
                    else:
                        conn.commit()
                        conn.close()
                        return jsonify({'success': True, 'message': f'支付确认成功，卡密已生成，但邮件发送失败: {send_msg}'})
            else:
                # 没有邮箱，只更新订单状态
                cursor.execute('UPDATE orders SET status = ? WHERE id = ?', ('completed', order_id))
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'message': '支付确认成功，请提醒用户完善邮箱信息'})
        else:
            return jsonify({'success': False, 'message': f'卡密生成失败: {gen_result}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'确认支付失败: {str(e)}'})

@app.route('/api/admin/order-groups/<int:order_group_id>/confirm-payment', methods=['POST'])
@admin_required
def admin_confirm_payment_group(order_group_id):
    """管理员手动确认订单组支付"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 检查订单组是否存在
        cursor.execute('SELECT * FROM order_groups WHERE id = ?', (order_group_id,))
        order_group = cursor.fetchone()
        
        if not order_group:
            conn.close()
            return jsonify({'success': False, 'message': '订单组不存在'})
        
        if order_group['status'] in ['paid', 'completed']:
            conn.close()
            return jsonify({'success': False, 'message': '订单组已经支付或完成'})
        
        # 获取订单组下的所有订单
        cursor.execute('SELECT id, user_id, status, card_key_id, bank_name FROM orders WHERE order_group_id = ?', (order_group_id,))
        orders = cursor.fetchall()
        
        if not orders:
            conn.close()
            return jsonify({'success': False, 'message': '订单组下没有订单'})
        
        # 更新订单组状态为已支付
        cursor.execute('UPDATE order_groups SET status = ?, paid_at = datetime("now") WHERE id = ?', ('paid', order_group_id))
        
        # 更新所有订单状态为已支付
        cursor.execute('UPDATE orders SET status = ?, paid_at = datetime("now") WHERE order_group_id = ?', ('paid', order_group_id))
        
        conn.commit()
        conn.close()
        
        # 为每个订单生成卡密
        card_keys = []
        for order in orders:
            gen_success, gen_result = db.generate_card_key_for_order(order['id'])
            if gen_success:
                card_keys.append({
                    'bank_name': order['bank_name'],
                    'card_key': gen_result['card_key']
                })
        
        # 重新获取连接来发送邮件
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 获取用户邮箱
        cursor.execute('SELECT email FROM users WHERE id = ?', (order_group['user_id'],))
        user = cursor.fetchone()
        
        if user and user['email']:
            # 发送卡密到邮箱
            card_keys_text = '\n'.join([f"银行：{ck['bank_name']}，卡密：{ck['card_key']}" for ck in card_keys])
            subject = f"您的卡密已到账 - 共{len(card_keys)}个"
            content = f"尊敬的用户：\n\n您的卡密已到账，请查收：\n\n{card_keys_text}\n\n请注意保管好您的卡密，如有问题请联系客服。"
            
            sender_id = session.get('user_id')
            send_success, send_msg = db.send_email(order_group['user_id'], sender_id, subject, content)
            
            if send_success:
                # 更新订单组状态为已完成
                cursor.execute('UPDATE order_groups SET status = ? WHERE id = ?', ('completed', order_group_id))
                # 更新所有订单状态为已完成
                cursor.execute('UPDATE orders SET status = ? WHERE order_group_id = ?', ('completed', order_group_id))
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'message': '支付确认成功，卡密已发送到用户邮箱'})
            else:
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'message': f'支付确认成功，卡密已生成，但邮件发送失败: {send_msg}'})
        else:
            # 没有邮箱，只更新订单状态
            cursor.execute('UPDATE order_groups SET status = ? WHERE id = ?', ('completed', order_group_id))
            cursor.execute('UPDATE orders SET status = ? WHERE order_group_id = ?', ('completed', order_group_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': '支付确认成功，请提醒用户完善邮箱信息'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'确认支付失败: {str(e)}'})

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/downloads')
def downloads_page():
    return render_template('downloads.html')

@app.route('/downloads/<filename>')
def download_file(filename):
    downloads_dir = os.path.join(app.root_path, 'downloads')
    
    # 安全验证：防止路径遍历攻击
    filename = os.path.basename(filename)
    if not filename:
        return jsonify({'success': False, 'message': '无效的文件名'}), 400
    
    # 检查文件是否在downloads目录中
    file_path = os.path.join(downloads_dir, filename)
    if not os.path.abspath(file_path).startswith(os.path.abspath(downloads_dir)):
        return jsonify({'success': False, 'message': '访问被拒绝'}), 403
    
    return send_from_directory(downloads_dir, filename, as_attachment=True)

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/orders')
@login_required
def orders_page():
    return render_template('orders.html')

@app.route('/emails')
@login_required
def emails_page():
    return render_template('emails.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/api/prices', methods=['GET'])
def get_prices():
    """获取所有价格配置（公开接口）"""
    try:
        prices = db.get_all_price_config()
        return jsonify({'success': True, 'data': prices})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取价格配置失败: {str(e)}'})

@app.route('/api/admin/prices', methods=['GET'])
@admin_required
def get_all_prices():
    """获取所有价格配置"""
    try:
        prices = db.get_all_price_config()
        return jsonify({'success': True, 'data': prices})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取价格配置失败: {str(e)}'})

@app.route('/api/admin/prices/<card_type>', methods=['PUT'])
@admin_required
def update_price(card_type):
    """更新价格配置"""
    try:
        data = request.json
        price = data.get('price')
        days_valid = data.get('days_valid')
        description = data.get('description')
        
        if price is None:
            return jsonify({'success': False, 'message': '价格不能为空'})
        
        success, message = db.update_price_config(card_type, price, days_valid, description)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新价格失败: {str(e)}'})

@app.route('/api/admin/prices', methods=['POST'])
@admin_required
def add_price():
    """添加价格配置"""
    try:
        data = request.json
        card_type = data.get('card_type')
        price = data.get('price')
        days_valid = data.get('days_valid')
        description = data.get('description', '')
        
        if not card_type or price is None or days_valid is None:
            return jsonify({'success': False, 'message': '卡密类型、价格和天数不能为空'})
        
        success, message = db.add_price_config(card_type, price, days_valid, description)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加价格失败: {str(e)}'})

@app.route('/api/admin/prices/<card_type>', methods=['DELETE'])
@admin_required
def delete_price(card_type):
    """删除价格配置"""
    try:
        success, message = db.delete_price_config(card_type)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除价格失败: {str(e)}'})

@app.route('/api/admin/update-admin-credentials', methods=['POST'])
@admin_required
def update_admin_credentials():
    """更新管理员账号密码"""
    try:
        data = request.json
        new_username = data.get('username')
        new_password = data.get('password')
        
        if not new_username or not new_password:
            return jsonify({'success': False, 'message': '用户名和密码不能为空'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM users WHERE is_admin = 1')
            
            new_password_hash = db.hash_password(new_password)
            cursor.execute('''
                INSERT INTO users (username, password, is_admin)
                VALUES (?, ?, ?)
            ''', (new_username, new_password_hash, 1))
            
            conn.commit()
            return jsonify({'success': True, 'message': '管理员账号密码更新成功'})
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新管理员账号失败: {str(e)}'})

@app.route('/api/payment/create', methods=['POST'])
@login_required
def create_payment():
    """创建支付订单并生成支付二维码"""
    data = request.json
    order_id = data.get('order_id')
    payment_method = data.get('payment_method')  # 'alipay' 或 'wechat'
    
    if not order_id:
        return jsonify({'success': False, 'message': '订单ID不能为空'})
    
    if not payment_method or payment_method not in ['alipay', 'wechat']:
        return jsonify({'success': False, 'message': '请选择支付方式'})
    
    try:
        # 获取订单信息
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, bank_name, card_type, days_valid, price, status
            FROM orders
            WHERE id = ?
        ''', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if not order:
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if order['status'] == 'completed':
            return jsonify({'success': False, 'message': '该订单已完成，无需支付'})
        
        # 生成支付二维码
        amount = order['price']
        qr_code_base64, qr_content = qr_generator.generate_payment_qrcode(
            payment_method=payment_method,
            amount=amount,
            order_id=order_id,
            description=f"{order['bank_name']}卡密"
        )
        
        # 创建支付记录
        success, result = db.create_payment(
            order_id=order_id,
            payment_method=payment_method,
            amount=amount,
            qr_code=qr_code_base64
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': '支付订单创建成功',
                'payment_id': result['payment_id'],
                'qr_code': qr_code_base64,
                'amount': amount,
                'payment_method': payment_method
            })
        else:
            return jsonify({'success': False, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'message': f'创建支付失败: {str(e)}'})

@app.route('/api/payment/complete', methods=['POST'])
@login_required
def complete_payment():
    """支付完成后处理（由支付回调触发）"""
    data = request.json
    order_id = data.get('order_id')
    transaction_id = data.get('transaction_id')
    
    if not order_id:
        return jsonify({'success': False, 'message': '订单ID不能为空'})
    
    try:
        # 获取支付记录
        payment = db.get_payment_by_order(order_id)
        
        if not payment:
            return jsonify({'success': False, 'message': '支付记录不存在'})
        
        if payment['status'] == 'completed':
            return jsonify({'success': False, 'message': '该订单已完成支付'})
        
        # 更新支付状态
        success, message = db.update_payment_status(payment['id'], 'completed', transaction_id)
        
        if success:
            # 生成卡密并发送到邮箱
            gen_success, gen_result = db.generate_card_key_for_order(order_id)
            
            if gen_success:
                # 获取用户信息
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT user_id, bank_name FROM orders WHERE id = ?', (order_id,))
                order_info = cursor.fetchone()
                conn.close()
                
                user = db.get_user_by_id(order_info['user_id'])
                if user and user.get('email'):
                    # 发送卡密到邮箱
                    send_success, send_msg = email_sender.send_card_key_email(
                        to_email=user['email'],
                        bank_name=order_info['bank_name'],
                        card_key=gen_result['card_key'],
                        days_valid=payment['amount']  # 这里需要根据实际情况调整
                    )
                    
                    if send_success:
                        # 更新订单状态为已完成
                        conn = db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE orders SET status = ? WHERE id = ?', ('completed', order_id))
                        conn.commit()
                        conn.close()
                        
                        return jsonify({
                            'success': True,
                            'message': '支付成功，卡密已发送到您的邮箱'
                        })
                    else:
                        return jsonify({
                            'success': True,
                            'message': '支付成功，但邮件发送失败，请联系客服',
                            'card_key': gen_result['card_key']
                        })
                else:
                    return jsonify({
                        'success': True,
                        'message': '支付成功，请完善邮箱信息以便接收卡密',
                        'card_key': gen_result['card_key']
                    })
            else:
                return jsonify({'success': False, 'message': f'卡密生成失败: {gen_result}'})
        else:
            return jsonify({'success': False, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'处理支付完成失败: {str(e)}'})

@app.route('/api/payment/simulate-success', methods=['POST'])
@login_required
def simulate_payment_success():
    """模拟支付成功（仅用于测试）"""
    data = request.json
    order_id = data.get('order_id')
    
    if not order_id:
        return jsonify({'success': False, 'message': '订单ID不能为空'})
    
    try:
        # 使用支付状态检测器模拟支付成功
        result = payment_checker.simulate_payment_success(order_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': '模拟支付成功',
                'payment': {
                    'order_id': order_id,
                    'status': 'completed',
                    'transaction_id': result.get('transaction_id')
                }
            })
        else:
            return jsonify({'success': False, 'message': result.get('message', '模拟支付失败')})
    except Exception as e:
        return jsonify({'success': False, 'message': f'模拟支付失败: {str(e)}'})

@app.route('/api/payment/check/<int:order_id>', methods=['GET'])
@login_required
def check_payment_status(order_id):
    """检查支付状态"""
    try:
        # 获取订单信息
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, status, user_id FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if not order:
            return jsonify({'success': False, 'message': '订单不存在'})
        
        # 检查订单是否属于当前用户
        if order['user_id'] != session['user_id']:
            return jsonify({'success': False, 'message': '无权查看此订单'})
        
        # 使用支付状态检测器检查状态
        result = payment_checker.check_payment_status(order_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'payment': {
                    'order_id': order_id,
                    'status': result['status'],
                    'message': result.get('message', '')
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('message', '检查支付状态失败')
            })
    except Exception as e:
        return jsonify({'success': False, 'message': f'检查支付状态失败: {str(e)}'})

@app.route('/api/payment/check-group/<int:order_group_id>', methods=['GET'])
@login_required
def check_order_group_payment_status(order_group_id):
    """检查订单组的支付状态"""
    try:
        # 获取订单组信息
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, status, user_id FROM order_groups WHERE id = ?', (order_group_id,))
        order_group = cursor.fetchone()
        conn.close()
        
        if not order_group:
            return jsonify({'success': False, 'message': '订单组不存在'})
        
        # 检查订单组是否属于当前用户
        if order_group['user_id'] != session['user_id']:
            return jsonify({'success': False, 'message': '无权查看此订单组'})
        
        # 使用支付状态检测器检查状态
        result = payment_checker.check_order_group_payment_status(order_group_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'payment': {
                    'order_group_id': order_group_id,
                    'status': result['status'],
                    'message': result.get('message', '')
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('message', '检查支付状态失败')
            })
    except Exception as e:
        return jsonify({'success': False, 'message': f'检查支付状态失败: {str(e)}'})

@app.route('/api/ympay/create', methods=['POST'])
@login_required
def create_ympay_payment():
    """创建YmPay订单"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        order_group_id = data.get('order_group_id')
        payment_type = data.get('type', 1)  # 1=支付宝, 2=微信支付, 3=QQ钱包
        
        if not order_id and not order_group_id:
            return jsonify({'success': False, 'message': '订单ID或订单组ID不能为空'})
        
        # 获取订单信息
        conn = db.get_connection()
        cursor = conn.cursor()
        
        if order_group_id:
            cursor.execute('''
                SELECT id, total_price, status, user_id
                FROM order_groups
                WHERE id = ?
            ''', (order_group_id,))
            order = cursor.fetchone()
            order_type = 'group'
            order_ref = order_group_id
        else:
            cursor.execute('''
                SELECT id, price, status, user_id
                FROM orders
                WHERE id = ?
            ''', (order_id,))
            order = cursor.fetchone()
            order_type = 'individual'
            order_ref = order_id
        
        conn.close()
        
        if not order:
            return jsonify({'success': False, 'message': '订单不存在'})
        
        if order['user_id'] != session['user_id']:
            return jsonify({'success': False, 'message': '无权操作此订单'})
        
        if order['status'] == 'paid':
            return jsonify({'success': False, 'message': '订单已支付'})
        
        amount = order['total_price'] if order_type == 'group' else order['price']
        
        # 构建回调URL
        base_url = request.host_url.rstrip('/')
        notify_url = f"{base_url}/api/ympay/notify"
        return_url = f"{base_url}/dashboard"
        
        # 创建YmPay订单
        ympay = ympay_config.get_ympay_instance()
        result = ympay.create_payment(
            order_id=order_ref,
            amount=amount,
            notify_url=notify_url,
            return_url=return_url,
            name=f'订单{order_ref}',
            type=payment_type
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'data': result['data'],
                'message': '支付订单创建成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('message', '创建支付订单失败')
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'创建支付订单失败: {str(e)}'})

@app.route('/api/ympay/notify', methods=['POST'])
@csrf.exempt
def ympay_notify():
    """YmPay回调通知"""
    try:
        params = request.form.to_dict()
        
        # 验证签名
        ympay = ympay_config.get_ympay_instance()
        if not ympay.verify_notify(params):
            return 'fail'
        
        # 获取订单信息
        trade_no = params.get('trade_no', '')
        out_trade_no = params.get('out_trade_no', '')
        total_fee = params.get('total_fee', '')
        trade_status = params.get('trade_status', '')
        
        if trade_status != 'TRADE_SUCCESS':
            return 'fail'
        
        # 判断是订单组还是单个订单
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 检查是否是订单组
        cursor.execute('''
            SELECT id, status, user_id
            FROM order_groups
            WHERE id = ?
        ''', (out_trade_no,))
        order_group = cursor.fetchone()
        
        if order_group:
            # 更新订单组状态
            if order_group['status'] != 'paid':
                cursor.execute('''
                    UPDATE order_groups
                    SET status = 'paid', paid_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (out_trade_no,))
                
                # 更新订单组下所有订单的状态
                cursor.execute('''
                    UPDATE orders
                    SET status = 'paid', paid_at = datetime('now', 'localtime')
                    WHERE order_group_id = ?
                ''', (out_trade_no,))
                
                conn.commit()
                conn.close()
                return 'success'
            else:
                conn.close()
                return 'success'
        
        # 检查是否是单个订单
        cursor.execute('''
            SELECT id, status, user_id
            FROM orders
            WHERE id = ?
        ''', (out_trade_no,))
        order = cursor.fetchone()
        
        if order:
            # 更新订单状态
            if order['status'] != 'paid':
                cursor.execute('''
                    UPDATE orders
                    SET status = 'paid', paid_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (out_trade_no,))
                
                conn.commit()
                conn.close()
                return 'success'
            else:
                conn.close()
                return 'success'
        
        conn.close()
        return 'fail'
        
    except Exception as e:
        logger.error(f"处理YmPay回调失败: {str(e)}")
        return 'fail'

@app.route('/api/ympay/config', methods=['GET', 'POST'])
@login_required
def ympay_config_api():
    """YmPay配置管理"""
    user_id = session.get('user_id')
    
    # 检查是否是管理员
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not user['is_admin']:
        return jsonify({'success': False, 'message': '无权访问'})
    
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'config': {
                'pid': ympay_config.pid,
                'gateway_url': ympay_config.gateway_url,
                'notify_url': ympay_config.notify_url,
                'return_url': ympay_config.return_url
            }
        })
    else:
        try:
            data = request.get_json()
            ympay_config.pid = data.get('pid')
            ympay_config.key = data.get('key')
            ympay_config.gateway_url = data.get('gateway_url', 'https://code.ymyu.cn')
            ympay_config.notify_url = data.get('notify_url')
            ympay_config.return_url = data.get('return_url')
            
            if ympay_config.save_config():
                return jsonify({'success': True, 'message': '配置保存成功'})
            else:
                return jsonify({'success': False, 'message': '配置保存失败'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'保存配置失败: {str(e)}'})

@app.route('/api/trial/check', methods=['GET'])
@login_required
def check_trial_usage():
    """检查体验卡是否已使用"""
    user_id = session.get('user_id')
    ip_address = request.remote_addr
    device_fingerprint = request.headers.get('User-Agent', '')
    
    has_used, usage_info = db.check_trial_usage(user_id, ip_address, device_fingerprint)
    
    return jsonify({
        'success': True,
        'has_used': has_used,
        'usage_info': usage_info
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)