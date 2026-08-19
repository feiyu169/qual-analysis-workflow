@echo off
rem ============================================================
rem  DSH Web 自启启动器（登录时运行，隐藏窗口，单实例）
rem  启动 DeepSeek Harness Web GUI: http://127.0.0.1:3080
rem  日志: <工作区>\.dsh-web.log
rem ============================================================
set "LOG=D:\OneDrive\文档\deepseek harness workspace\.dsh-web.log"

rem 已在监听 3080 则直接退出
netstat -ano | findstr ":3080" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo %date% %time% DSH Web already running, skip. >> "%LOG%"
  exit /b 0
)

echo %date% %time% Starting DSH Web... >> "%LOG%"

rem 隐藏窗口启动 dsh web（detached，不依赖本 cmd 生命周期）
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command ^
  "& 'C:\Users\79902\AppData\Local\npm-cache\_npx\1e7f6d9597241db0\node_modules\.bin\dsh.cmd' web *>> 'D:\OneDrive\文档\deepseek harness workspace\.dsh-web.log' 2>&1"

exit /b 0
