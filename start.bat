@echo off
chcp 65001
CALL %USERPROFILE%\anaconda3\Scripts\activate.bat solara-develop
python main.py
pause