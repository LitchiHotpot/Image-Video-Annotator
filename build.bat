@echo off
REM ============================================================
REM  Build a SLIM standalone Annotator.exe with PyInstaller.
REM
REM  Two tricks keep the exe small and the build reliable:
REM   1. Build inside a clean virtualenv (pip numpy uses small
REM      OpenBLAS instead of Anaconda's huge MKL) with headless
REM      OpenCV  ->  ~85 MB instead of ~320 MB.
REM   2. Build in an ASCII temp folder, because PyInstaller's Qt
REM      hook fails when the project path has non-ASCII (e.g. CJK)
REM      characters. The finished exe is copied back to .\dist.
REM
REM  Just run:  build.bat
REM ============================================================
setlocal
set "SRC=%~dp0"
set "WORK=%TEMP%\annotator_build"

echo === Preparing clean build folder: %WORK% ===
rmdir /s /q "%WORK%" 2>nul
mkdir "%WORK%"
copy /y "%SRC%main.py"        "%WORK%\" >nul
copy /y "%SRC%canvas.py"      "%WORK%\" >nul
copy /y "%SRC%media.py"       "%WORK%\" >nul
copy /y "%SRC%pair_window.py" "%WORK%\" >nul

echo === Creating virtualenv and installing minimal deps ===
python -m venv "%WORK%\venv"
"%WORK%\venv\Scripts\python.exe" -m pip install --upgrade pip
"%WORK%\venv\Scripts\python.exe" -m pip install PyQt5 opencv-python-headless numpy pyinstaller

echo === Building exe ===
pushd "%WORK%"
"%WORK%\venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed ^
  --name Annotator ^
  --exclude-module matplotlib --exclude-module scipy --exclude-module pandas ^
  --exclude-module PIL --exclude-module tkinter --exclude-module pytest ^
  --exclude-module IPython --exclude-module sympy ^
  main.py
popd

echo === Copying exe back to .\dist ===
if not exist "%SRC%dist" mkdir "%SRC%dist"
copy /y "%WORK%\dist\Annotator.exe" "%SRC%dist\Annotator.exe" >nul

echo.
echo Done. The exe is at: %SRC%dist\Annotator.exe
endlocal
pause
