@echo off
echo ================================
echo   Job Apply Agent Starting...
echo ================================
cd /d "D:\Repostories\job-apply-agent"
call venv\Scripts\activate.bat
python run.py
pause
