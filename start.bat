@echo off
echo ============================================
echo  FIFA World Cup 2026 Sweepstake Server
echo ============================================
echo.

:: Install dependencies if needed
pip install -r requirements.txt --quiet

echo Starting server...
echo.
echo  Open this address on ANY PC on your network:
echo.

:: Print the local IP address
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
  set IP=%%a
  goto :found
)
:found
set IP=%IP: =%
echo     http://%IP%:5000
echo.
echo  (You can also use http://localhost:5000 on this machine)
echo.
echo  Press Ctrl+C to stop the server.
echo ============================================
echo.

python app.py
pause

