#!/bin/bash
echo "========================================="
echo "  Agent Monitor - Pre-Install Check"
echo "========================================="
echo ""

echo "--- OS ---"
uname -a
echo ""

echo "--- Python ---"
if command -v python3 &> /dev/null; then
    python3 --version
    echo "  PASS"
else
    echo "  FAIL: Python3 not found"
    echo "  Fix: sudo apt install python3 (Ubuntu) or brew install python3 (Mac)"
fi
echo ""

echo "--- pip ---"
if python3 -m pip --version &> /dev/null; then
    python3 -m pip --version
    echo "  PASS"
else
    echo "  FAIL: pip not found"
    echo "  Fix: sudo apt install python3-pip (Ubuntu)"
fi
echo ""

echo "--- venv ---"
if python3 -m venv --help &> /dev/null; then
    echo "  PASS"
else
    echo "  FAIL: venv module not found"
    echo "  Fix: sudo apt install python3-venv (Ubuntu)"
fi
echo ""

echo "--- git ---"
if command -v git &> /dev/null; then
    git --version
    echo "  PASS"
else
    echo "  FAIL: git not found"
    echo "  Fix: sudo apt install git (Ubuntu) or brew install git (Mac)"
fi
echo ""

echo "--- Network: Dashboard Server ---"
if curl -s --max-time 5 http://172.16.0.146:5000/ > /dev/null 2>&1; then
    echo "  PASS: 172.16.0.146:5000 reachable"
else
    echo "  FAIL: Cannot reach 172.16.0.146:5000"
    echo "  Check: Are you on the office network?"
fi
echo ""

echo "--- Network: GitHub ---"
if curl -s --max-time 5 https://github.com > /dev/null 2>&1; then
    echo "  PASS: github.com reachable"
else
    echo "  FAIL: Cannot reach github.com"
    echo "  Check: Internet connection or proxy settings"
fi
echo ""

echo "========================================="
echo "  All PASS = Ready to install extension"
echo "  Any FAIL = Fix before installing"
echo "========================================="
