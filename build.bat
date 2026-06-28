@echo off
REM Build a standalone Windows .exe with PyInstaller.
REM Run from this folder:  build.bat

echo === Installing dependencies ===
pip install -r requirements.txt
pip install pyinstaller

echo === Building exe ===
pyinstaller --noconfirm --onefile --windowed ^
  --name "Annotator" ^
  --collect-submodules cv2 ^
  main.py

echo.
echo Done. The exe is in the "dist" folder: dist\Annotator.exe
pause
