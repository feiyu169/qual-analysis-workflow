# Flask Project Skeleton Generation

> 从设计文档生成完整 Flask 项目骨架的模式
> Verified: 2026-06-12

## 目录结构模板

```
project-name/
├── app/
│   ├── __init__.py          # 应用工厂
│   ├── api/                 # API 蓝图
│   │   ├── __init__.py
│   │   ├── auth.py         # 认证模块
│   │   ├── [domain].py     # 业务模块
│   │   └── upload.py       # 文件上传
│   ├── models/
│   │   └── __init__.py     # SQLAlchemy 模型
│   ├── services/
│   │   └── [domain]_service.py  # 业务逻辑
│   └── utils/
│       ├── auth_utils.py   # 认证工具
│       ├── error_handlers.py
│       └── jwt_callbacks.py
├── config/
│   └── config.py           # 环境配置
├── migrations/
│   └── 001_init_schema.sql # 建表 + 初始数据
├── scripts/
│   └── init.sh             # 初始化脚本
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py                  # 主入口
└── README.md
```

## 关键实现模式

### 1. 应用工厂 (app/__init__.py)

```python
def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    db.init_app(app)
    jwt.init_app(app)
    CORS(app)
    
    # 注册蓝图
    from app.api import auth, exceptions
    app.register_blueprint(auth.bp, url_prefix='/api/v1/auth')
    app.register_blueprint(exceptions.bp, url_prefix='/api/v1/exceptions')
    
    return app
```

### 2. 数据库模型 (app/models/__init__.py)

每个表一个类，包含：
- 字段定义（类型、约束、索引）
- to_dict() 方法用于序列化
- 关联关系（relationship）

### 3. 业务服务层 (app/services/)

将业务逻辑从 API 路由中分离：
- 状态机流转逻辑
- 业务规则校验
- 事务管理
- 操作日志记录

### 4. API 路由 (app/api/)

```python
@bp.route('', methods=['POST'])
@jwt_required()
@require_role(['admin', 'user'])
def create_item():
    data = request.get_json()
    # 调用 service 层
    item = ItemService.create(data, get_current_user())
    return jsonify({'code': 200, 'data': item.to_dict()})
```

### 5. 权限控制装饰器

```python
def require_role(roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') not in roles:
                return jsonify({'code': 403, 'message': '无权限'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
```

### 6. 数据库迁移脚本

```sql
-- 启用外键约束（SQLite）
PRAGMA foreign_keys = ON;

-- 建表
CREATE TABLE IF NOT EXISTS ...

-- 索引
CREATE INDEX IF NOT EXISTS ...

-- 初始数据
INSERT OR IGNORE INTO ...
```

## 代码生成顺序

1. **配置文件** - config.py, .env.example
2. **数据库迁移** - 001_init_schema.sql（建表 + 初始数据）
3. **数据模型** - models/__init__.py
4. **应用工厂** - app/__init__.py, run.py
5. **工具函数** - auth_utils, error_handlers, jwt_callbacks
6. **业务服务** - services/[domain]_service.py
7. **API 路由** - api/auth.py, api/[domain].py
8. **辅助文件** - requirements.txt, README.md, .gitignore, scripts/init.sh

## 后续开发步骤

```bash
# 1. 初始化环境
bash scripts/init.sh

# 2. 启动开发服务器
python run.py

# 3. 测试 API
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```
