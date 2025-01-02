from flask import Flask
from src.api.routes import register_routes
from src.utils.config import Config
from src.utils.credentials_manager import CredentialsManager
import os

def create_app():
    config = Config()
    app = Flask(__name__)
    
    # Use config values instead of hardcoded values
    app.config['PROJECT_ID'] = config.get('project', 'id')
    app.config['REGION'] = config.get('project', 'region')
    app.config['MIN_INSTANCES'] = config.get('cloud_run', 'min_instances')
    app.config['MAX_INSTANCES'] = config.get('cloud_run', 'max_instances')
    
    # Initialize credentials manager
    app.cred_manager = CredentialsManager(app.config['PROJECT_ID'])
    
    register_routes(app)
    return app

def main():
    app = create_app()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    main() 