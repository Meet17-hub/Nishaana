@echo off
REM Start both Flask backend and Next.js frontend for Lakshya cyberpunk dashboard
REM With independent RIFLE and PISTOL scoring systems

REM Change to the cyberpunk-dashboard-design directory
cd /d "%~dp0"

echo ============================================================
echo Starting Lakshya Dashboard (Rifle + Pistol - Independent)
echo ============================================================
echo.
echo Architecture:
echo  - scripts/ folder: RIFLE scoring system only
echo  - scripts_pistol/ folder: PISTOL scoring system only
echo  - Next.js Frontend: Unified dashboard for both modes
echo  - Consolidated database (users.db, users.json in root)
echo  - Direct imports, no dynamic module switching
echo.

REM Start Manager and underlying Flask backend in a new window
echo Starting Manager + initial Flask Backend on port 5000/5005...
start "Flask Manager + Backend" cmd /k "python manager.py"

REM Wait a moment for Flask to start
timeout /t 3 /nobreak

REM Start Next.js frontend in a new window
echo Starting Next.js frontend on port 3000...
start "Next.js Frontend" cmd /k "npm run dev"

echo.
echo ============================================================
echo Servers are starting in separate windows...
echo.
echo MANAGER (Router): http://127.0.0.1:5005 (manager.py)
echo BACKEND API: http://127.0.0.1:5000 (app.py)
echo Next.js Frontend: http://localhost:3000
echo.
echo Scoring:
echo  - RIFLE: 1.5 ring hole size (3.41mm)
echo  - PISTOL: 4.32mm hole size
echo  - Both with center dot + ring circle visualization
echo.
echo Database Location: ./users.db (consolidated root directory)
echo ============================================================
echo.
pause
