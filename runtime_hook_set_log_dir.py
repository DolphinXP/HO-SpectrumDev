import os
import sys

if getattr(sys, 'frozen', False):
    # Running as compiled executable
    executable_dir = os.path.dirname(sys.executable)
else:
    # Running as script
    executable_dir = os.path.dirname(os.path.abspath(__file__))

# Set log directory to a 'logs' subdirectory next to the executable/script
log_dir = os.path.join(executable_dir, "logs")
os.environ['APP_LOG_DIR'] = log_dir
