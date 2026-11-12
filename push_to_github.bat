@echo off
title Push ValidBridge to GitHub
cd /d "D:\ValidBridge"
echo ========================================================
echo Pushing ValidBridge to:
echo https://github.com/vamedicasubmissions-dotcom/validbridge-.git
echo ========================================================
echo.

git init
git branch -M main
git add .
git commit -m "Initial release of ValidBridge core platform (validbridge.com)"
git remote remove origin >nul 2>&1
git remote add origin https://github.com/vamedicasubmissions-dotcom/validbridge-.git
echo.
echo Pushing to GitHub...
git push -u origin main

echo.
echo ========================================================
echo Done! Code is now live on GitHub.
echo ========================================================
pause
