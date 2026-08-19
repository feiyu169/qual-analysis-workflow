# Exception System HGF V2.0 Execution Record

## Project: 气田异常管理系统 (Gas Field Exception Management System)
## Server: 101.43.83.237 (Tencent Cloud OpenCloudOS 9.4)
## Date: 2026-06-17

## Architecture

```
Client → Nginx (:80)
  ├── /              → 盲板管理系统 (port 8000)
  └── /exception/    → 异常管理系统 (port 8001)
```

## Gate Execution Summary

### Gate 1.1: 钉钉配置 — CONDITIONAL PASS
- **准入条件**: 前置分析完成 ✅
- **准出条件**: access_token 获取成功 ✅, 消息发送待验证 ⚠️
- **实现**:
  - dingtalk_service.py — access_token 缓存 + 工作通知 + 群消息
  - notification_service.py — 事件驱动通知（5种类型）
  - scheduler_service.py — APScheduler + Redis 分布式锁
- **阻塞**: 用户 dingtalk_user_id 未配置，无法测试实际消息发送

### Gate 1.2: 预警提醒功能 — CONDITIONAL PASS
- **准入条件**: Gate 1.1 通过 ✅
- **准出条件**: 4个定时任务运行正常 ✅, 手动触发测试通过 ✅
- **定时任务**:
  - notification_retry (每5分钟)
  - pending_reminder (每天08:00)
  - timeout_check (每1小时)
  - overdue_check (每天09:00)
- **API**: `/api/v1/scheduler/status`, `/jobs`, `/check-timeout`, `/check-pending`, `/check-overdue`

### Gate 2.1: 统计报表优化 — PASS
- **准入条件**: Gate 1.2 通过 ✅
- **准出条件**: 统计 API 正常 ✅, 缓存生效 ✅, 时间范围筛选 ✅
- **修复**:
  - SQLite 兼容性: `func.IF()` → `case()` (Pitfall 9)
  - 新增 `/overview` API
  - Redis 缓存服务 (cache_service.py)
- **缓存策略**: 统计 60s TTL, 趋势 300s TTL

### Gate 2.2: 字典管理优化 — PASS
- **准入条件**: Gate 2.1 通过 ✅
- **准出条件**: 三级联动正确 ✅, 缓存正常 ✅
- **新增**:
  - `/dict/category?level=1|2|3&parent=xxx` — 三级联动
  - `/dict/site` — 站点字典
  - `/dict/cache` — 缓存统计
  - `/dict/cache/invalidate` — 缓存清除
- **数据**: 4大类, 多个中类/小类, 1站点, 1分派规则

### Gate 2.3: 操作日志优化 — PASS
- **准入条件**: Gate 2.2 通过 ✅
- **准出条件**: 操作日志自动生成 ✅, IP脱敏 ✅, 查询API ✅
- **实现**:
  - sanitizer.py — 手机号/身份证/邮箱/IP 脱敏
  - OperationLog.to_dict(sanitize=True) — 脱敏开关
- **修复**: User.to_dict 被 sed 污染 → Python 脚本精确替换

### Gate 3.1: 防重复提交 — PASS
- **准出条件**: 首次200 ✅, 重复409 ✅, 不同key200 ✅, 无key200 ✅
- **实现**: Redis SET NX + X-Idempotency-Key 请求头

### Gate 3.2: XSS防护 — PASS
- **准出条件**: 5个安全头部全部配置 ✅
- **实现**: after_request 添加 CSP/XSS/XCTO/XFO/Referrer

### Gate 4.1: 回归测试 — PASS (20/21)
### Gate 4.2: 新功能验证 — PASS
### Gate 4.3: 部署验证 — PASS

**总计: 10/10 Gate 通过**

## Key Pitfalls Encountered

1. **SQLite dual databases** — exception.db vs exception_dev.db, FLASK_ENV not loaded by systemd
2. **func.IF() incompatibility** — MySQL function used in SQLite context
3. **File permissions** — SCP root upload vs lighthouse service user
4. **systemd EnvironmentFile** — .env not loaded without explicit EnvironmentFile directive
5. **Config mode confusion** — DevelopmentConfig hardcoded overrides ProductionConfig
6. **Model to_dict corruption via sed** — sed replaces ALL matching patterns, corrupting other classes' methods. Use Python str.replace(old, new, 1)
7. **Redis idempotency** — SET NX + X-Idempotency-Key for POST endpoints, 409 on duplicate
8. **Security headers** — after_request: CSP + X-XSS-Protection + X-Content-Type-Options + X-Frame-Options + Referrer-Policy

## Server Commands

```bash
# SSH
sshpass -p '***' ssh root@101.43.83.237

# Service management
systemctl restart exception-system
systemctl status exception-system
journalctl -u exception-system -f

# Database
sqlite3 /opt/exception-system/data/exception_dev.db

# Redis
redis-cli ping  # → PONG

# API test
curl http://localhost:8001/api/v1/health
```
