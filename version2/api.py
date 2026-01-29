from flask import Flask

app = Flask(__name__)

@app.route('/status')
def status():
    return "Agent is running "

# New feature: log viewer
@app.route('/logs')
def view_logs():
    with open('.agent/logs/2026-01-29.log') as f:
        return f.read()

# Another violation: database connection
import sqlite3 

def get_db():
    conn = sqlite3.connect('agent.db')
    return conn 

if __name__ == "__main__":
    app.run(port=5000)
