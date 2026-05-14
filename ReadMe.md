Steps to Download the packages

**Windows:**
pip install -r requirements.txt

**macOS:**
pip3 install -r requirements.txt

**macOS (Tk / GUI):** Do not rely on `/usr/bin/python3` if the window crashes with `macOS 26 … required, have instead 16 …` (Xcode CLT Python + Tk mismatch). Prefer:

```bash
brew install python@3.14 python-tk@3.14
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt   # use the same brew python’s pip
./run_sdm_gui_macos.sh
```

Or install [python.org macOS installer](https://www.python.org/downloads/macos/) (bundles Tcl/Tk 8.6).

**Linux:**
# System dependencies first
sudo apt-get update
sudo apt-get install python3-tk python3-pip build-essential
 
pip3 install -r requirements.txt

<img width="1221" height="250" alt="image" src="https://github.com/user-attachments/assets/d01a8260-65c4-4a77-9241-76dfc3bd838f" />
