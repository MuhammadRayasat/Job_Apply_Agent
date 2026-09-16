@echo off
echo ================================
echo   Job Apply Agent Starting...
echo ================================
cd /d "D:\Repostories\job-apply-agent"
call venv\Scripts\activate.bat
venv\Scripts\python.exe -m playwright install chromium --quiet 2>nul
python run.py
pause
