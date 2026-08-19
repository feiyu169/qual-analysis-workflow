# Tencent Cloud Co-Deployment Pattern

## Scenario

Deploying a new service alongside an existing service on the same Tencent Cloud server.

## Verified Pattern (2026-06-17)

### Server: 101.43.83.237 (OpenCloudOS 9.4)

**Existing service**: blind-plate-system (port 8000, Nginx on port 80)
**New service**: exception-system (port 8001, Nginx on /exception/)

### Step 1: Check existing services
```bash
sshpass -p 'PASSWORD' ssh -o StrictHostKeyChecking=no root@SERVER "
  systemctl list-units --type=service --state=running
  ss -tlnp | grep -E ':(80|443|3000|8000|8001|8080)'
  cat /etc/nginx/conf.d/*.conf
"
```

### Step 2: Choose non-conflicting port
```bash
# Check what ports are in use
ss -tlnp | grep LISTEN

# Use a free port (e.g., 8001)
```

### Step 3: Deploy with different port
```python
# In run.py or equivalent
app.run(host='0.0.0.0', port=8001, debug=False)
```

### Step 4: Configure Nginx reverse proxy
```nginx
# Add location block INSIDE existing server block
server {
    listen 80;
    server_name _;
    
    # Existing service
    location / {
        root /opt/existing-app/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
    
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }
    
    # New service (add this)
    location /exception/api/ {
        proxy_pass http://127.0.0.1:8001/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /exception/ {
        alias /opt/new-app/frontend/dist/;
        index index.html;
        try_files $uri $uri/ /exception/index.html;
    }
}
```

### Step 5: Frontend base path configuration

**Vite (vite.config.js)**:
```javascript
export default defineConfig({
  base: '/exception/',  // Add this
  // ...
})
```

**Vue Router**:
```javascript
const router = createRouter({
  history: createWebHistory('/exception/'),  // Add base path
  routes
})
```

**Axios baseURL**:
```javascript
const request = axios.create({
  baseURL: '/exception/api/v1',  // Include base path
  timeout: 30000
})
```

### Step 6: Create systemd service
```ini
[Unit]
Description=New App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/new-app
Environment="PATH=/opt/new-app/venv/bin"
ExecStart=/opt/new-app/venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Pitfalls

### P0: Frontend base path mismatch

**Symptom**: Frontend loads but API calls go to wrong path (e.g., /api/v1 instead of /exception/api/v1)

**Fix**: Configure base path in THREE places:
1. vite.config.js → `base: '/exception/'`
2. router/index.js → `createWebHistory('/exception/')`
3. utils/request.js → `baseURL: '/exception/api/v1'`

### P1: Nginx location block outside server block

**Symptom**: `nginx: [emerg] "location" directive is not allowed here`

**Fix**: Add location blocks INSIDE the server {} block, not after it.

### P2: Database path confusion (dev vs prod)

**Symptom**: Data not persisting or "table not found" errors

**Root cause**: Two databases exist (exception.db and exception_dev.db)

**Fix**: Check which database the config points to:
```bash
cat .env | grep DATABASE_URL
# Ensure it points to the correct database
```
