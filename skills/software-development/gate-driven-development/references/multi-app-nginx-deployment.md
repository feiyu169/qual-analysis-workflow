# Multi-App Nginx Reverse Proxy Deployment

## Problem
Deploying multiple applications (e.g., exception-system + blind-plate-system) on the same server with a single Nginx entry point.

## Architecture
```
Client → Nginx (port 80)
  ├─ /           → blind-plate-system (port 8000)
  └─ /exception/ → exception-system (port 8001)
```

## Nginx Config (alias-based routing)

```nginx
server {
    listen 80;
    server_name _;
    client_max_body_size 10m;

    # App 1: blind-plate-system (default)
    location / {
        root /opt/blind-plate/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # App 2: exception-system (sub-path)
    location /exception/api/ {
        proxy_pass http://127.0.0.1:8001/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /exception/ {
        alias /opt/exception-system/frontend/dist/;
        index index.html;
        try_files $uri $uri/ /exception/index.html;
    }
}
```

## Key Pitfalls

### P1: `location` outside `server` block
Appending `location /exception/ {}` AFTER the `server {}` closing brace → `nginx: [emerg] "location" directive is not allowed here`. Use `sed` to insert BEFORE the last `}`:

```bash
sed -i '/^}/i\
\
    # Exception Management System\
    location /exception/ {\
        ...\
    }' /etc/nginx/conf.d/app.conf
```

### P2: `alias` requires trailing slash
```nginx
# ✗ WRONG — missing trailing slash
location /exception/ {
    alias /opt/app/dist;  # 404 on assets
}

# ✓ CORRECT
location /exception/ {
    alias /opt/app/dist/;  # trailing slash required
}
```

### P3: `try_files` with alias
When using `alias`, `try_files` paths are relative to the alias target:
```nginx
location /exception/ {
    alias /opt/app/dist/;
    try_files $uri $uri/ /exception/index.html;  # ← /exception/ prefix needed
}
```

### P4: API proxy path rewriting
Strip the prefix when proxying:
```nginx
# Request: /exception/api/v1/auth/login
# Proxied to: http://127.0.0.1:8001/api/v1/auth/login
location /exception/api/ {
    proxy_pass http://127.0.0.1:8001/api/;  # ← trailing slash strips prefix
}
```

### P5: Frontend base path must match
The frontend's router base and Vite base must match the URL path:
```javascript
// vite.config.js
export default defineConfig({
  base: '/exception/',  // ← must match nginx location
})

// router/index.js
const router = createRouter({
  history: createWebHistory('/exception/'),  // ← must match
})
```

### P6: API baseURL must include sub-path
```javascript
// src/utils/request.js
const request = axios.create({
  baseURL: '/exception/api/v1',  // ← must include /exception/ prefix
})
```

## Verification Checklist
```
□ nginx -t passes
□ Frontend loads: curl -s http://server/exception/ | grep '<title>'
□ API works: curl -s http://server/exception/api/v1/health
□ Login works: curl -X POST http://server/exception/api/v1/auth/login ...
□ Static assets load: curl -s -I http://server/exception/assets/index-*.js
□ Original app unaffected: curl -s http://server/ | grep '<title>'
```
