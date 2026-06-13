@echo off
cd /d "%~dp0"

rem Open browser after a short delay
start "" /b cmd /c "timeout /t 2 >nul && start http://localhost:5027"

echo Starting DanaSim Viewer at http://localhost:5027 ...
DanaSim.Viewer.Web.exe %*
