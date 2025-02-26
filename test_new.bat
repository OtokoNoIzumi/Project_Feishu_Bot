@echo off
chcp 65001
CALL %USERPROFILE%\anaconda3\Scripts\activate.bat workspace
python main_new.py
pause