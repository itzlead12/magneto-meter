$ErrorActionPreference = "Stop"

python -m pip install -r requirements-build.txt
python -m PyInstaller --clean --onefile --windowed --name AP230-Magnetometer main.py
