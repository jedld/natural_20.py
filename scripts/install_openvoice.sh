#!/bin/bash
# install_openvoice.sh - Patched installation for Python 3.11+ / 3.13
#
# OpenVoice has several incompatible dependencies:
# 1. numpy==1.22.0 - doesn't support Python 3.12+
# 2. faster-whisper==0.9.0 -> requires av==10.* (Cython exception incompatibility)
# 3. Various exact version pins that conflict with modern Python
#
# This script clones the repo, patches all requirements, and installs locally.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== OpenVoice Patched Installer ==="
echo "Python version: $(python --version)"
echo "Project directory: $PROJECT_DIR"

# Clone OpenVoice to a local directory
OPENVOICE_DIR="$PROJECT_DIR/.local_packages/OpenVoice"
if [ -d "$OPENVOICE_DIR" ]; then
    echo "OpenVoice already cloned at $OPENVOICE_DIR, using existing clone."
else
    echo "Cloning OpenVoice..."
    git clone --depth 1 https://github.com/myshell-ai/OpenVoice.git "$OPENVOICE_DIR"
fi

# Navigate to OpenVoice directory
cd "$OPENVOICE_DIR"

# Patch setup.py - the PRIMARY source of dependency pins
echo "Patching setup.py for modern dependency versions..."
cat > /tmp/openvoice_setup_patch.py << 'PYTHON_SCRIPT'
import re

setup_path = "setup.py"
with open(setup_path, "r") as f:
    content = f.read()

# Replace exact version pins with minimum versions
replacements = [
    ("librosa==0.9.1", "librosa>=0.10.0"),
    ("faster-whisper==0.9.0", "faster-whisper>=1.0.0"),
    ("pydub==0.25.1", "pydub>=0.25.1"),
    ("wavmark==0.0.3", "wavmark>=0.0.3"),
    ("eng_to_ipa==0.0.2", "eng_to_ipa>=0.0.2"),
    ("inflect==7.0.0", "inflect>=7.0.0"),
    ("unidecode==1.3.7", "unidecode>=1.3.7"),
    ("whisper-timestamped==1.14.2", "whisper-timestamped>=1.14.2"),
    ("pypinyin==0.50.0", "pypinyin>=0.50.0"),
    ("cn2an==0.5.22", "cn2an>=0.5.22"),
    ("jieba==0.42.1", "jieba>=0.42.1"),
    ("gradio==3.48.0", "gradio>=4.0.0"),
    ("langid==1.1.6", "langid>=1.1.6"),
]

for old, new in replacements:
    content = content.replace(old, new)

# Ensure numpy allows modern versions
content = re.sub(r'numpy==1\.22\.0', 'numpy>=1.24.0', content)

with open(setup_path, "w") as f:
    f.write(content)

print("  - Patched setup.py")
PYTHON_SCRIPT
python /tmp/openvoice_setup_patch.py

# Also patch requirements.txt if it exists
if [ -f "requirements.txt" ]; then
    echo "Patching requirements.txt..."
    sed -i 's/librosa==0\.9\.1/librosa>=0.10.0/g' requirements.txt
    sed -i 's/faster-whisper==0\.9\.0/faster-whisper>=1.0.0/g' requirements.txt
    sed -i 's/av==10\.*/av>=12.0.0/g' requirements.txt
    sed -i 's/numpy==1\.22\.0/numpy>=1.24\.0/g' requirements.txt
    echo "  - Patched requirements.txt"
fi

# Install the patched version in editable mode
echo ""
echo "Installing patched OpenVoice..."
pip install -e .

# Verify installation
echo ""
echo "=== Verifying Installation ==="
python -c "
try:
    import av
    print(f'  av version: {av.__version__}')
except ImportError as e:
    print(f'  WARNING: av import failed: {e}')

try:
    from openvoice.api import BaseSpeakerTTS
    print('  OpenVoice BaseSpeakerTTS: OK')
except ImportError as e:
    print(f'  WARNING: OpenVoice import failed: {e}')

try:
    import torch
    print(f'  PyTorch version: {torch.__version__}')
except ImportError as e:
    print(f'  WARNING: PyTorch import failed: {e}')
"

echo ""
echo "=== Installation Complete ==="
echo "OpenVoice installed at: $OPENVOICE_DIR"
echo ""
echo "Next steps:"
echo "  1. Test import: python -c 'from openvoice.api import BaseSpeakerTTS; print(\"OK\")'"
echo "  2. Configure TTS in your environment (see user_levels/death_house/TTS_SETUP_GUIDE.md)"
echo "  3. Run the server with TTS_ENABLED=1"
