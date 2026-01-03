#!/bin/bash
set -e

echo "========================================"
echo "启动银行纪念币预约助手系统"
echo "========================================"

# 设置数据库路径为绝对路径
export DATABASE_PATH="/app/data/bank_card_system.db"

# 创建数据目录
mkdir -p /app/data /app/logs

echo "数据库路径: $DATABASE_PATH"
echo "工作目录: $(pwd)"
echo "Python 版本: $(python --version)"
echo "========================================"

# 检查环境变量
echo "检查环境变量..."
echo "SECRET_KEY: ${SECRET_KEY:0:10}..."
echo "DEBUG: $DEBUG"
echo "PORT: $PORT"
echo "========================================"

# 尝试导入应用并检查错误
echo "测试应用导入..."
python -c "import app; print('应用导入成功')" || {
    echo "应用导入失败，检查错误..."
    python -c "import app" 2>&1 || true
    exit 1
}

echo "========================================"
echo "启动 Gunicorn 服务器..."
echo "========================================"

# 启动 Gunicorn
exec gunicorn \
    --bind 0.0.0.0:${PORT:-5000} \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app:app
