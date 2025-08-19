#!/usr/bin/env python3
"""
ML Training Workflow Script
Combines data preparation and model training into a single workflow
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description='ML Training Workflow: Prepare data and train model',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Prepare data from Firestore and train model
  python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3

  # Load from specific users with date filter
  python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3 \\
    --user-ids 5oZfUgtSn0g1VaEa6VNpHVC51Zq2 aDer8RS94NPmPdAYGHQQpI3iWm13 \\
    --start-date 2024-01-01

  # Load from BigQuery with filters
  python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3 --source bigquery --limit 10000

  # Just prepare data without training
  python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3 --prepare-only

  # Just train model (assumes data already exists)
  python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3 --train-only

  # Test locally with sample data
  python scripts/ml_training_workflow.py --local-test

  # Use standard tier resources for production
  python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3 --no-free-tier
        """
    )
    
    parser.add_argument('--project-id', help='GCP project ID')
    parser.add_argument('--source', choices=['firestore', 'bigquery'], default='firestore',
                       help='Data source for training data preparation')
    parser.add_argument('--prepare-only', action='store_true',
                       help='Only prepare data, skip training')
    parser.add_argument('--train-only', action='store_true',
                       help='Only train model, skip data preparation')
    parser.add_argument('--local-test', action='store_true',
                       help='Run local test with sample CSV data')
    parser.add_argument('--model-name', default=None,
                       help='Model name for deployment (default: transaction_model_vYYYYMMDD)')
    parser.add_argument('--no-free-tier', action='store_true',
                       help='Use standard tier resources instead of cost-optimized')
    parser.add_argument('--deploy-target', choices=['cloud_function', 'vertex_ai'], default='cloud_function',
                        help='Where to deploy the trained model: cloud_function (default) or vertex_ai')
    
    # Data filtering options
    parser.add_argument('--user-id', help='Filter by single user ID (deprecated, use --user-ids)')
    parser.add_argument('--user-ids', nargs='+', help='Filter by multiple user IDs')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, help='Limit number of records per user')
    parser.add_argument('--dataset', default='financial_tracker', help='BigQuery dataset ID')
    parser.add_argument('--table', default='transactions', help='BigQuery table ID')
    parser.add_argument('--collection', default='transactions', help='Firestore collection name')
    
    args = parser.parse_args()
    
    # Handle local test mode
    if args.local_test:
        logger.info("Running local test with sample data...")
        from train_models_locally import main as test_locally
        test_locally()
        return
        
    # Validate project ID for cloud operations
    if not args.project_id:
        parser.error("--project-id is required unless using --local-test")
        
    # Generate model name if not provided
    if not args.model_name:
        args.model_name = f"transaction_model_v{datetime.now().strftime('%Y%m%d')}"
        
    logger.info(f"ML Training Workflow for project: {args.project_id}")
    logger.info(f"Model name: {args.model_name}")
    
    try:
        # Step 1: Prepare training data (unless train-only)
        if not args.train_only:
            logger.info("\n" + "="*60)
            logger.info("STEP 1: Preparing Training Data")
            logger.info("="*60)
            
            from prepare_ml_training_data import MLDataPreparer
            
            preparer = MLDataPreparer(args.project_id)
            
            # Build kwargs for data preparation
            kwargs = {}
            if args.source == 'firestore':
                kwargs['collection'] = args.collection
            else:  # bigquery
                kwargs['dataset_id'] = args.dataset
                kwargs['table_id'] = args.table
                
            # Add filters
            if args.user_id:
                kwargs['user_id'] = args.user_id
            if args.user_ids:
                kwargs['user_ids'] = args.user_ids
            if args.start_date:
                # Parse date string to datetime
                kwargs['start_date'] = datetime.strptime(args.start_date, '%Y-%m-%d')
            if args.end_date:
                # Parse date string to datetime
                kwargs['end_date'] = datetime.strptime(args.end_date, '%Y-%m-%d')
            if args.limit:
                kwargs['limit'] = args.limit
                
            # Prepare data
            output_path = preparer.prepare_training_data(source=args.source, **kwargs)
            
            if not output_path:
                logger.error("No data was prepared. Exiting.")
                sys.exit(1)
                
            logger.info(f"Training data prepared: {output_path}")
            
            if args.prepare_only:
                logger.info("\nData preparation complete. Skipping training (--prepare-only flag set)")
                return
                
        # Step 2: Train and deploy model (unless prepare-only)
        if not args.prepare_only:
            logger.info("\n" + "="*60)
            logger.info("STEP 2: Training and Deploying Model")
            logger.info("="*60)
            
            from src.models.transaction_trainer import TransactionModelTrainer
            
            # Determine free tier setting
            use_free_tier = not args.no_free_tier  # Command line flag takes precedence
            
            # If not specified on command line, read from config
            if not args.no_free_tier:
                try:
                    import yaml
                    with open('config.yaml', 'r') as f:
                        config = yaml.safe_load(f)
                        use_free_tier = config.get('project', {}).get('use_free_tier', True)
                except:
                    use_free_tier = True  # Default to cost-optimized
            
            logger.info(f"Using {'cost-optimized' if use_free_tier else 'standard'} tier resources")
            trainer = TransactionModelTrainer(args.project_id, use_free_tier=use_free_tier)
            
            logger.info(f"Training model: {args.model_name}")
            logger.info("This may take several minutes...")
            
            model, endpoint = trainer.train_and_deploy_model(args.model_name, deploy_target=args.deploy_target)

            if args.deploy_target == 'vertex_ai' and model and endpoint:
                logger.info(f"\nModel trained and deployed successfully!")
                logger.info(f"Model: {model.resource_name}")
                logger.info(f"Endpoint: {endpoint.resource_name}")
            else:
                logger.info("\nModel trained and artifacts uploaded. Use the Cloud Function for inference.")
            
        logger.info("\n" + "="*60)
        logger.info("Workflow Complete!")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Error in workflow: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 