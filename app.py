# import dependencies
import os
from flask import Flask
from threading import Thread
from time import sleep

def scan_loop():
    while True:
        print('this is where I would scan a file')
        sleep(5)


Thread(target=scan_loop, daemon=True).start()

# bootstrap the app
app = Flask(__name__)

port = int(os.getenv('PORT', '8080'))

# our base route which just returns a string
@app.route('/')
def hello_world():
    return 'Temporary Flask App to ensure Terraform Apply Occurs'

# start the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)
