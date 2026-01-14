@echo off
echo Starting Dashboard Server...
echo Please open http://localhost:8080/dashboard.html in your browser.
cd /d "c:\Users\A\Project_Feishu_Bot"
python -m http.server 8080 --directory web
pause
