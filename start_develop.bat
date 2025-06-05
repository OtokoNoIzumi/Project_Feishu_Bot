@echo off
chcp 65001
CALL %USERPROFILE%\anaconda3\Scripts\activate.bat WorkSpace
python mai.py
pause