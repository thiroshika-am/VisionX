@echo off
REM Install PyTorch with CUDA 12.1 support for NVIDIA GPU
REM This will replace the CPU-only version with GPU-accelerated version

echo ============================================
echo Installing PyTorch with CUDA Support
echo ============================================
echo.

REM First, uninstall CPU version
echo Removing CPU-only PyTorch...
pip uninstall torch torchvision torchaudio -y

echo.
echo Installing GPU-accelerated PyTorch (CUDA 12.1)...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo.
echo Verifying CUDA installation...
python -c "import torch; print(f'PyTorch Version: {torch.__version__}'); print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

echo.
echo ============================================
echo Installation complete!
echo ============================================
pause
