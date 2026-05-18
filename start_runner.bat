@echo off
title Qorvai AI - 24/7 Lead Runner
echo.
echo  ==========================================
echo   Qorvai AI - 24/7 Continuous Runner
echo  ==========================================
echo.

REM Load .env
if exist .env (
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set %%a=%%b
    )
)

echo  Running 24/7 — scrapes every 60 min, all niches, all locations
echo  Logs: runner.log
echo  Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe continuous_runner.py --interval 60
pause
