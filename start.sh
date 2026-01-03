#!/bin/bash
set -e

echo "========================================"
echo "启动银行纪念币预约助手系统"
echo "========================================"

# 创建数据目录
mkdir -p /app/data /app/logs

echo "工作目录: $(pwd)"
echo "Python 版本: $(python --version)"
echo "端口: ${PORT:-5000}"
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
