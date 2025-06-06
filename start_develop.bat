@echo off
chcp 65001
echo 启动飞书机器人 (开发模式)...
CALL %USERPROFILE%\anaconda3\Scripts\activate.bat WorkSpace
python main.py --verify-api --http-api
pause