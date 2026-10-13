@echo off
"%SystemRoot%\System32\chcp.com" 65001 >nul
setlocal
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto check_python
set "PYTHON_EXE=python"
"%PYTHON_EXE%" -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 goto check_dependencies
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
:check_python
"%PYTHON_EXE%" -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 goto check_dependencies
echo 未找到 Python 3.11 或更新版本。
echo 请安装带 Tcl/Tk 的 Python，并勾选 Add Python to PATH，然后重新双击本文件。
echo 下载地址：https://www.python.org/downloads/windows/
pause
exit /b 2
:check_dependencies
"%PYTHON_EXE%" "%~dp0examples\factor_research.py" --check
if not errorlevel 1 goto launch
echo.
echo 可在项目目录运行以下命令安装依赖，然后重新双击：
echo cd /d "%~dp0"
echo "%PYTHON_EXE%" -m pip install -e ".[research]"
pause
exit /b 2
:launch
"%PYTHON_EXE%" "%~dp0examples\factor_research.py"
if not errorlevel 1 exit /b 0
pause
exit /b 2
