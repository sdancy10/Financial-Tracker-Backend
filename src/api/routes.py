from flask import request, jsonify
from src.utils.transaction_dao import TransactionDAO
from src.services.transaction_trainer import TransactionModelTrainer
from src.utils.config import Config
from google.cloud import secretmanager

def register_routes(app):
    @app.route('/process', methods=['POST'])
    def process_transactions():
        try:
            dao = TransactionDAO(app.config['PROJECT_ID'])
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({"status": "error", "message": "No user_id provided"}), 400
                
            success = dao.get_email_data(userid=user_id)
            if not success:
                return jsonify({"status": "error", "message": "Failed to process emails"}), 500
                
            success = dao.post_db_data(userid=user_id)
            if not success:
                return jsonify({"status": "error", "message": "Failed to save transactions"}), 500
                
            return jsonify({
                "status": "success", 
                "processed": len(dao.transaction_dict_results)
            }), 200
                
        except secretmanager.NotFoundError:
            return jsonify({
                "status": "error", 
                "message": "Credentials not found for user"
            }), 404
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/train', methods=['POST'])
    def train_model():
        try:
            config = Config()
            trainer = TransactionModelTrainer(
                project_id=app.config['PROJECT_ID'],
                region=app.config['REGION']
            )
            model, endpoint = trainer.train_and_deploy_model(
                model_display_name=config.get('model', 'model_name')
            )
            return jsonify({
                "status": "success",
                "model_id": model.name,
                "endpoint": endpoint.resource_name
            }), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500 