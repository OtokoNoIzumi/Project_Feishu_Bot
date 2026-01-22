@echo off
chcp 65001 >nul
CALL "%USERPROFILE%\anaconda3\Scripts\activate.bat" WorkSpace

REM 说明：此脚本需要以 UTF-8-BOM 编码保存

REM 切到项目根目录（apps 的上一级），确保可以 import `apps`
cd /d "%~dp0.."

set BACKEND_HOST=0.0.0.0
set BACKEND_PORT=7701
REM Optional: enable internal auth by setting a token, then call with:
REM Authorization: Bearer <token>
REM If not set in the environment, keep it empty (auth disabled).
if not defined BACKEND_INTERNAL_TOKEN set BACKEND_INTERNAL_TOKEN=

REM Optional: SSL (HTTPS) for direct uvicorn. Certs are in project root.
REM IMPORTANT: Do NOT use SSL_CERT_FILE as variable name - it conflicts with
REM Python httpx library which uses it for CA certificate verification!
set SSL_ENABLE=true
set "UVICORN_KEY_FILE=%CD%\izumiai.site.key"
set "UVICORN_CERT_FILE=%CD%\izumiai.site.pem"

set "UVICORN_SSL_ARGS="
if /I "%SSL_ENABLE%"=="true" (
    if exist "%UVICORN_KEY_FILE%" if exist "%UVICORN_CERT_FILE%" (
        set "UVICORN_SSL_ARGS=--ssl-keyfile ""%UVICORN_KEY_FILE%"" --ssl-certfile ""%UVICORN_CERT_FILE%"""
        echo HTTPS enabled: %UVICORN_CERT_FILE%
    ) else (
        echo WARN: SSL enabled but certs not found. Falling back to HTTP.
    )
)

python -m uvicorn apps.app:app --host %BACKEND_HOST% --port %BACKEND_PORT% %UVICORN_SSL_ARGS%
pause
