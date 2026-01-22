@echo off
chcp 65001 >nul
CALL "%USERPROFILE%\anaconda3\Scripts\activate.bat" WorkSpace

REM 说明：此脚本需要以 UTF-8-BOM 编码保存

REM 切到项目根目录（apps 的上一级），确保可以 import `apps`
cd /d "%~dp0.."

set BACKEND_HOST=127.0.0.1
set BACKEND_PORT=7701
REM Optional: enable internal auth by setting a token, then call with:
REM Authorization: Bearer <token>
set BACKEND_INTERNAL_TOKEN=

python -m uvicorn apps.app:app --host %BACKEND_HOST% --port %BACKEND_PORT%
pause


