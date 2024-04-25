# A very basic flask app to get the health check working for cgov and terraform. Due to this, the health check is
# currently port based. We should change this in the future, however, for now, this is fine.

import os
from flask import Flask

app = Flask(__name__)
port = int(os.getenv('PORT', '8080'))

@app.route('/')
def hello_world():
    return 'Temporary Flask App to ensure Terraform Apply Occurs'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)
