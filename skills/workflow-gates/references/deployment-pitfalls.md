# 部署常见陷阱和解决方案

## 文件权限问题

### 问题: SCP上传文件权限不正确

**现象**: `PermissionError: [Errno 13] Permission denied`

**原因**: SCP上传文件默认为root权限，但服务以其他用户（如lighthouse）运行

**解决**:
```bash
# 修复单个文件
chown lighthouse:lighthouse /path/to/file
chmod 755 /path/to/file

# 修复整个目录
chown -R lighthouse:lighthouse /opt/app
chmod -R 755 /opt/app
```

**预防**: 在部署脚本中始终包含权限修复步骤

## SQLite兼容性问题

### 问题: MySQL函数在SQLite中不可用

**现象**: `sqlite3.OperationalError: no such function: IF`

**原因**: SQLite不支持MySQL的`IF()`函数

**解决**: 使用SQLAlchemy的`case()`函数替代
```python
# 错误 (MySQL only)
func.sum(func.IF(ExceptionRecord.status == '待接收', 1, 0))

# 正确 (SQLite兼容)
from sqlalchemy import case
func.sum(case((ExceptionRecord.status == '待接收', 1), else_=0))
```

### 问题: SQLite并发写入限制

**现象**: 高并发下写入失败或超时

**原因**: SQLite使用文件级锁，不支持并发写入

**解决**:
- 开发/测试: 使用SQLite（单用户场景）
- 生产: 使用PostgreSQL/MySQL（支持并发写入）

## 模型字段错误

### 问题: sed命令替换范围过大

**现象**: `AttributeError: 'User' object has no attribute 'exception_id'`

**原因**: sed命令替换了错误的代码块

**解决**: 使用Python脚本进行精确替换，避免sed的贪婪匹配
```python
with open('file.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 精确替换
old_code = '''def to_dict(self):
    return {
        "id": self.id,
        "exception_id": self.exception_id,
        ...'''

new_code = '''def to_dict(self):
    return {
        "id": self.id,
        "username": self.username,
        ...'''

content = content.replace(old_code, new_code, 1)

with open('file.py', 'w', encoding='utf-8') as f:
    f.write(content)
```

## 数据库配置问题

### 问题: 测试环境与生产环境数据库不一致

**现象**: 测试数据丢失，字典数据不一致

**原因**: 开发环境使用`exception_dev.db`，生产环境使用`exception.db`

**解决**:
- 统一数据库配置，使用环境变量
- 测试环境使用独立数据库
- 部署前验证数据库路径

### 问题: systemd服务未加载环境变量

**现象**: 服务使用开发配置而非生产配置

**原因**: systemd服务未配置`EnvironmentFile`

**解决**:
```ini
# /etc/systemd/system/app.service
[Unit]
Description=App Service
After=network.target

[Service]
Type=simple
User=lighthouse
WorkingDirectory=/opt/app
Environment="PATH=/opt/app/venv/bin"
EnvironmentFile=/opt/app/.env  # 添加这行
ExecStart=/opt/app/venv/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Redis连接问题

### 问题: Redis连接失败

**现象**: `redis.exceptions.ConnectionError`

**原因**: Redis服务未启动或配置错误

**解决**:
```bash
# 检查Redis状态
redis-cli ping

# 启动Redis
systemctl start redis

# 检查配置
grep REDIS_HOST /opt/app/.env
```

## 部署检查清单

```
部署前:
  [ ] 文件权限正确 (chown -R lighthouse:lighthouse)
  [ ] 环境变量配置正确 (EnvironmentFile)
  [ ] 数据库路径正确 (DATABASE_URL)
  [ ] Redis连接正常 (redis-cli ping)
  [ ] 服务能正常启动 (systemctl status)

部署后:
  [ ] 健康检查通过 (curl /api/v1/health)
  [ ] 核心功能可用 (登录、创建、查询)
  [ ] 日志无错误 (journalctl -u app)
  [ ] 性能指标正常 (响应时间<500ms)
```
