# 验证脚本模式

Gate 验证中常用的 shell/Python 模式，避免 P6/P7 pitfall。

## 文件大小检查
```bash
F=$(stat -c%s "$path")  # Linux
[[ $F -gt 10000 ]] && echo "✓" || echo "✗"
```

## exit_code 检查（不用 grep 中文）
```bash
python3 test.py > /dev/null 2>&1
[[ $? -eq 0 ]] && echo "PASS" || echo "FAIL"
```

## JSON 输出验证
```bash
cmd > /tmp/out.json 2>&1; EXIT=$?
[[ $EXIT -eq 0 ]] || { echo "FAIL: exit=$EXIT"; exit 1; }
VALUE=$(python3 -c "import json; print(json.load(open('/tmp/out.json'))['key'])")
```

## 数值范围验证
```bash
python3 -c "
v = $VALUE
assert 0.05 < v < 0.15, f'WACC {v} out of range'
print(f'✓ WACC={v}')
"
```

## 全链路验证（calc→excel→state）
```bash
# Step 1: calc
cd $base/finance-calc && python3 scripts/calc_engine.py wacc '{...}' > /tmp/w.json 2>&1
WACC=$(python3 -c "import json; print(json.load(open('/tmp/w.json'))['wacc'])")

# Step 2: calc → excel
cd $base/excel-builder && python3 scripts/excel_builder.py build "{\"template\":\"dcf\",\"data\":{...},\"output\":\"/tmp/out.xlsx\"}" > /dev/null 2>&1

# Step 3: state put → get → verify
cd $base/state-store && python3 scripts/state_store.py put '{"ns":"test","key":"k","value":{"ps":128}}' > /dev/null 2>&1
GET=$(cd $base/state-store && python3 scripts/state_store.py get '{"ns":"test","key":"k"}')
PS=$(echo "$GET" | python3 -c "import sys,json; print(json.load(sys.stdin)['value']['ps'])")
[[ "$PS" == "128" ]] && echo "✓ state 一致" || echo "✗ state 不一致"
```

## 批量 Skill 合规检查
```bash
# 检查所有 Skill 是否含免责声明
PASS=0; FAIL=0
for skill in dcf comps lbo 3stmt morning-note; do
  if grep -q '免责\|不构成投资' "$base/$skill/SKILL.md" 2>/dev/null; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "✗ $skill 缺免责声明"
  fi
done
echo "免责声明: $PASS 通过, $FAIL 失败"
```

## Cron Job 验证
```bash
# 创建后检查
hermes cron list | grep "job-name"
# 手动触发
hermes cron run <job_id>
# 等待执行后检查
sleep 30 && hermes cron list | grep "job-name"  # 检查 last_status
```
