# 测试自动化框架设计（V3.0）

## 技术栈

```
pytest 7.x + pytest-xdist + allure-pytest
requests 2.x | marshmallow (Schema) | factory_boy + faker
pytest-mock + responses >= 0.24 | pytest-timeout | pytest-repeat | pytest-rerunfailures
GitHub Actions CI/CD
```

## 目录结构

```
tests/
├── conftest.py                 # 全局fixtures (session-scoped clients, db_validator, cleanup)
├── pytest.ini                  # markers: smoke/functional/boundary/workflow/concurrent/security/performance
├── config/
│   ├── settings.py             # 环境配置 (BASE_URL, DB_PATH)
│   ├── test_users.py           # 测试用户定义
│   └── endpoints.py            # API端点常量
├── schemas/                    # 响应Schema (marshmallow)
│   ├── common.py               # BaseResponse, SuccessResponse, ErrorResponse, PaginatedResponse, ListResponse
│   ├── exception.py            # ExceptionData, ExceptionResponse
│   └── ...
├── utils/
│   ├── api_client.py           # 统一API封装 (login, get/post/put/delete, assert_success/error)
│   ├── db_validator.py         # SQLite直接查询验证 (assert_exception_exists, assert_field_value)
│   ├── assertions.py           # 自定义断言 (assert_schema验证, assert_success带expected_code参数)
│   ├── data_factory.py         # 测试数据工厂 (ExceptionFactory.create, idempotency_key)
│   └── idempotency.py          # 幂等键生成器
├── fixtures/
│   ├── auth.py                 # api_client, admin_client, reporter_client, handler_client
│   ├── exceptions.py           # test_exception (自动清理)
│   └── cleanup.py              # autouse cleanup fixture
├── test_smoke/                 # L1: 健康检查, 登录, 基本CRUD
├── test_functional/            # L2: auth, exceptions, dict, statistics, scheduler, operation_logs
├── test_boundary/              # L3: pagination, input, permission
├── test_workflow/              # L4: forward(正向), reject(驳回), invalid(非法转换), permission
├── test_concurrent/            # L5: idempotency, race_condition, load
├── test_security/              # L6: xss, sql_injection, auth_bypass, idor, headers
└── test_performance/           # L7: response_time, throughput, resource
```

## Schema设计要点

```python
# 所有Schema必须设置 Meta: unknown = EXCLUDE
# 防止API新增字段导致marshmallow ValidationError，门禁误报
class ExceptionData(Schema):
    class Meta:
        unknown = EXCLUDE  # 必须！
    id = fields.Int(required=True)
    # ...
```

## Fixtures设计要点

```python
@pytest.fixture(scope="session")
def admin_client(api_client):
    api_client.login("admin", "admin123")
    return api_client

@pytest.fixture
def test_exception(admin_client, db_validator):
    """自动创建+清理"""
    data = ExceptionFactory.create()
    resp = admin_client.post("/api/v1/exceptions", json=data)
    yield resp.json()["data"]
    db_validator.delete_exception(resp.json()["data"]["id"])
```

## assert_success设计

```python
def assert_success(response, schema_class=None, expected_code=200):
    data = response.json()
    assert data["code"] == expected_code
    if schema_class:
        assert_schema(data, schema_class)
    return data
```

## GitHub Actions集成

```yaml
# .github/workflows/test.yml
jobs:
  gate-t0:
    steps:
      - uses: actions/checkout@v3
      - run: pip install -r requirements-test.txt
      - run: python scripts/run_gate.py T0
  gate-t1:
    needs: gate-t0
    steps:
      - run: python scripts/run_gate.py T1
  gate-t2:
    needs: gate-t1
    if: startsWith(github.ref, 'refs/tags/')
    steps:
      - run: python scripts/run_gate.py T2
```

## Gate T执行脚本

```python
# scripts/run_gate.py
GATE_CONFIG = {
    "T0": {"markers": ["smoke"], "pass_rate": 1.0, "timeout": 120},
    "T1": {"markers": ["functional", "boundary"], "pass_rate": 1.0, "timeout": 600},
    "T2": {"markers": ["workflow", "concurrent", "security"], "pass_rate": 0.98, "timeout": 1800},
    "T3": {"markers": ["smoke", "functional", "boundary", "workflow"], "pass_rate": 0.99, "timeout": 3600},
}
```

## HeavySkill审查发现的关键问题

1. Schema必须设unknown=EXCLUDE，否则API变更导致门禁误报
2. CI/CD必须第2天就搭建，不能拖到第8天
3. 安全测试用环境依赖的应标记skip/xfail，不计入失败率
4. 并发测试需pytest-rerunfailures处理偶发失败
5. 门禁失败需要SLA（T0/T1: 4h, T2: 24h, T3: 48h）
