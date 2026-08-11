@echo off
cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python -c "import streamlit" 2>nul || (
    echo Installing requirements...
    pip install -r requirements.txt
)

echo.
echo AutoSeller starting...
echo Open http://localhost:8501 in your browser
echo.

if exist "venv\Scripts\streamlit.exe" (
    venv\Scripts\streamlit.exe run gui\app.py --server.port 8501 --server.headless false
) else (
    streamlit run gui\app.py --server.port 8501 --server.headless false
)
