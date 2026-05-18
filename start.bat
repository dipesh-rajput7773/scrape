@echo off
title Qorvai AI - Lead Engine
echo.
echo  ==========================================
echo   Qorvai AI - Intelligent Lead Engine
echo  ==========================================
echo.

REM Load .env if it exists
if exist .env (
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set %%a=%%b
    )
)

REM Start the Streamlit dashboard
echo  Starting dashboard at http://localhost:8501
echo  Press Ctrl+C to stop.
echo.
venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
pause
