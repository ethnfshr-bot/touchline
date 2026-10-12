@echo off
rem Drag a match video onto this file to tag it automatically.
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag a match video file onto "Analyse match.bat" to analyse it.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo The video tool isn't set up yet. See pipeline\README.md, "Setup".
  pause
  exit /b 1
)
echo Touchline video tool
echo Analysing: %~nx1
echo.
set /p US="Your team's shirt colour (e.g. navy, red, white): "
set /p THEM="Opposition shirt colour: "
echo.
echo This takes a while (roughly as long as the video). You can leave it running.
echo.
".venv\Scripts\python.exe" -m touchline_cv.analyse "%~1" --us "%US%" --them "%THEM%"
echo.
pause
