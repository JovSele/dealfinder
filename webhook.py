from flask import Flask, request
import subprocess

app = Flask(__name__)

@app.route('/deploy', methods=['POST'])
def deploy():
    subprocess.run(['git', 'pull'], cwd='/opt/dealfinder')
    subprocess.run(['docker-compose', 'up', '-d', '--build', 'scraper'], cwd='/opt/dealfinder')
    return 'OK'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
