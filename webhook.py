from flask import Flask, request
import subprocess
app = Flask(__name__)

@app.route('/deploy', methods=['POST'])
def deploy():
    subprocess.run(['git', 'pull'], cwd='/opt/dealfinder')
    subprocess.run(['docker', 'build', '--no-cache', '-t', 'dealfinder-scraper', '/opt/dealfinder'])
    subprocess.run(['docker', 'stop', 'dealfinder_scraper_1'])
    subprocess.run(['docker', 'rm', 'dealfinder_scraper_1'])
    subprocess.run(['docker', 'run', '-d', '--name', 'dealfinder_scraper_1', 
                    '--env-file', '/opt/dealfinder/.env',
                    '--network', 'dealfinder_default',
                    'dealfinder-scraper'])
    return 'OK'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
