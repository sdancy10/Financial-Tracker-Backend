from flask import Blueprint, request, jsonify
from src.services.ml_prediction_service import MLPredictionService
from src.services.ml_feedback_service import MLFeedbackService
from src.utils.transaction_dao import TransactionDAO
from typing import Dict, Any
import logging

# Create blueprint
ml_bp = Blueprint('ml', __name__, url_prefix='/api/v1/ml')

# Set up logging
logger = logging.getLogger(__name__)

# Services will be initialized with app context
ml_prediction_service = None
ml_feedback_service = None
transaction_dao = None


def init_services(project_id: str):
    """Initialize services with project ID"""
    global ml_prediction_service, ml_feedback_service, transaction_dao
    ml_prediction_service = MLPredictionService(project_id)
    ml_feedback_service = MLFeedbackService(project_id)
    transaction_dao = TransactionDAO(project_id)


@ml_bp.route('/predict', methods=['POST'])
def predict_categories():
    """Batch prediction endpoint for transaction categories"""
    try:
        data = request.get_json()
        
        if not data or 'transactions' not in data:
            return jsonify({
                'error': 'Missing transactions data'
            }), 400
        
        transactions = data['transactions']
        if not isinstance(transactions, list):
            return jsonify({
                'error': 'Transactions must be a list'
            }), 400
        
        # Make predictions
        predictions = ml_prediction_service.predict_categories(transactions)
        
        return jsonify({
            'predictions': predictions,
            'model_version': ml_prediction_service.get_current_model_version()
        }), 200
        
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        return jsonify({
            'error': 'Prediction failed',
            'message': str(e)
        }), 500


@ml_bp.route('/feedback', methods=['POST'])
def submit_feedback():
    """Submit category correction feedback"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['transaction_id', 'user_id', 'new_category']
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Update transaction category (this will also record feedback)
        success = transaction_dao.update_transaction_category(
            transaction_id=data['transaction_id'],
            user_id=data['user_id'],
            new_category=data['new_category'],
            new_subcategory=data.get('new_subcategory'),
            old_category=data.get('old_category'),
            old_subcategory=data.get('old_subcategory')
        )
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Category updated and feedback recorded'
            }), 200
        else:
            return jsonify({
                'error': 'Failed to update category'
            }), 500
            
    except Exception as e:
        logger.error(f"Feedback error: {e}", exc_info=True)
        return jsonify({
            'error': 'Feedback submission failed',
            'message': str(e)
        }), 500


@ml_bp.route('/metrics', methods=['GET'])
def get_model_metrics():
    """Get current model performance metrics"""
    try:
        # Get query parameters
        days = request.args.get('days', 30, type=int)
        include_categories = request.args.get('include_categories', 'false').lower() == 'true'
        
        # Get model metrics from ML service
        model_metrics = ml_prediction_service.get_model_metrics()
        
        # Get feedback statistics
        feedback_stats = ml_feedback_service.get_feedback_stats(days=days)
        
        response = {
            'model_version': ml_prediction_service.get_current_model_version(),
            'model_metrics': model_metrics,
            'feedback_stats': feedback_stats
        }
        
        # Include category-specific accuracy if requested
        if include_categories:
            category_accuracy = ml_feedback_service.get_category_accuracy(
                model_version=ml_prediction_service.get_current_model_version()
            )
            response['category_accuracy'] = category_accuracy
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Metrics error: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to get metrics',
            'message': str(e)
        }), 500


@ml_bp.route('/model/info', methods=['GET'])
def get_model_info():
    """Get information about the current deployed model"""
    try:
        is_available = ml_prediction_service.is_available()
        model_version = ml_prediction_service.get_current_model_version()
        
        return jsonify({
            'available': is_available,
            'model_version': model_version,
            'status': 'active' if is_available else 'unavailable'
        }), 200
        
    except Exception as e:
        logger.error(f"Model info error: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to get model info',
            'message': str(e)
        }), 500


@ml_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all available categories from recent transactions"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({
                'error': 'Missing user_id parameter'
            }), 400
        
        # Get categories from transaction DAO
        categories = transaction_dao.get_categories(user_id)
        
        return jsonify({
            'categories': categories
        }), 200
        
    except Exception as e:
        logger.error(f"Categories error: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to get categories',
            'message': str(e)
        }), 500


# Error handlers
@ml_bp.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404


@ml_bp.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}", exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500 