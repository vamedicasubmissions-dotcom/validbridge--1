@echo off
title ValidBridge Portal Launcher
cd /d "D:\ValidBridge"
start "ValidBridge Server" "C:\Users\Yasuk\AppData\Local\Programs\Python\Python313\python.exe" server.py
timeout /t 2 /nobreak >nul
start http://localhost:8080/
echo ValidBridge is running at http://localhost:8080/
