Pre-check:

# OS	    Command
Mac/Linux	curl -sL https://raw.githubusercontent.com/prakyath-ux/monitoring_agent/version2/scripts/precheck.sh | bash

# Windows	
curl -sL https://raw.githubusercontent.com/prakyath-ux/monitoring_agent/version2/scripts/precheck.bat -o %TEMP%\precheck.bat && %TEMP%\precheck.bat


# Cleanup (if agent-monitor already exists):

OS	                Command
Mac/Linux	        rm -rf ~/.agent-monitor
Windows	            rmdir /s /q %USERPROFILE%\.agent-monitor


# Debug (when extension fails):

OS	                        Command
Mac/Linux	                python3 ~/.agent-monitor/version2/jetbrains-loader.py start /path/to/project
Windows	                    python %USERPROFILE%\.agent-monitor\version2\jetbrains-loader.py start "D:\path\to\project"
