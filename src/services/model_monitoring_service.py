from google.cloud import monitoring_v3, bigquery, firestore
from google.cloud.monitoring_dashboard import v1
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Any, Optional
import json

class ModelMonitoringService:
    """Service for monitoring ML model performance and metrics"""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.monitoring_client = monitoring_v3.MetricServiceClient()
        self.dashboard_client = v1.DashboardsServiceClient()
        self.bigquery = bigquery.Client(project=project_id)
        self.firestore = firestore.Client(project=project_id)
        self.logger = logging.getLogger(__name__)
        
        # Metric paths
        self.project_path = f"projects/{project_id}"
        self.metric_type_prefix = "custom.googleapis.com/ml"
        
    def write_model_metric(self, metric_name: str, value: float, 
                          labels: Optional[Dict[str, str]] = None):
        """Write a custom metric to Cloud Monitoring"""
        try:
            # Create time series
            series = monitoring_v3.TimeSeries()
            series.metric.type = f"{self.metric_type_prefix}/{metric_name}"
            
            # Add labels
            if labels:
                for key, val in labels.items():
                    series.metric.labels[key] = str(val)
            
            # Set resource
            series.resource.type = "global"
            series.resource.labels["project_id"] = self.project_id
            
            # Add data point
            now = datetime.utcnow()
            seconds = int(now.timestamp())
            nanos = int((now.timestamp() % 1) * 10**9)
            
            interval = monitoring_v3.TimeInterval(
                {"end_time": {"seconds": seconds, "nanos": nanos}}
            )
            point = monitoring_v3.Point({
                "interval": interval,
                "value": {"double_value": value}
            })
            series.points = [point]
            
            # Write time series
            self.monitoring_client.create_time_series(
                name=self.project_path,
                time_series=[series]
            )
            
            self.logger.info(f"Wrote metric {metric_name}: {value}")
            
        except Exception as e:
            self.logger.error(f"Error writing metric: {e}")
    
    def track_prediction_metrics(self):
        """Track real-time prediction metrics"""
        try:
            # Query recent predictions
            query = f"""
            WITH hourly_metrics AS (
                SELECT 
                    TIMESTAMP_TRUNC(created_at, HOUR) as hour,
                    model_version,
                    COUNT(*) as predictions,
                    AVG(prediction_confidence) as avg_confidence,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT predicted_category) as unique_categories
                FROM `{self.project_id}.{self._get_dataset_id()}.training_data`
                WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                GROUP BY hour, model_version
            )
            SELECT * FROM hourly_metrics
            ORDER BY hour DESC
            """
            
            query_job = self.bigquery.query(query)
            
            for row in query_job:
                labels = {"model_version": row.model_version}
                
                # Write metrics
                self.write_model_metric("predictions_per_hour", row.predictions, labels)
                self.write_model_metric("avg_confidence", row.avg_confidence, labels)
                self.write_model_metric("unique_users", row.unique_users, labels)
                self.write_model_metric("category_diversity", row.unique_categories, labels)
                
        except Exception as e:
            self.logger.error(f"Error tracking prediction metrics: {e}")
    
    def track_feedback_metrics(self):
        """Track user feedback and model accuracy"""
        try:
            query = f"""
            WITH feedback_metrics AS (
                SELECT 
                    DATE(feedback_timestamp) as date,
                    model_version,
                    COUNT(*) as feedback_count,
                    SUM(CASE WHEN original_category = user_category THEN 1 ELSE 0 END) as correct,
                    COUNT(DISTINCT user_id) as users_providing_feedback
                FROM `{self.project_id}.{self._get_dataset_id()}.ml_feedback`
                WHERE feedback_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
                GROUP BY date, model_version
            )
            SELECT 
                *,
                ROUND(correct / feedback_count, 3) as accuracy
            FROM feedback_metrics
            ORDER BY date DESC
            """
            
            query_job = self.bigquery.query(query)
            
            for row in query_job:
                labels = {
                    "model_version": row.model_version,
                    "date": row.date.strftime("%Y-%m-%d")
                }
                
                # Write metrics
                self.write_model_metric("feedback_count", row.feedback_count, labels)
                self.write_model_metric("accuracy", row.accuracy, labels)
                self.write_model_metric("users_providing_feedback", 
                                      row.users_providing_feedback, labels)
                
        except Exception as e:
            self.logger.error(f"Error tracking feedback metrics: {e}")
    
    def track_category_performance(self):
        """Track performance by category"""
        try:
            query = f"""
            SELECT 
                predicted_category,
                model_version,
                COUNT(*) as predictions,
                AVG(prediction_confidence) as avg_confidence
            FROM `{self.project_id}.{self._get_dataset_id()}.training_data`
            WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
            GROUP BY predicted_category, model_version
            HAVING predictions > 10
            ORDER BY predictions DESC
            """
            
            query_job = self.bigquery.query(query)
            
            for row in query_job:
                labels = {
                    "category": row.predicted_category,
                    "model_version": row.model_version
                }
                
                self.write_model_metric("category_predictions", row.predictions, labels)
                self.write_model_metric("category_confidence", row.avg_confidence, labels)
                
        except Exception as e:
            self.logger.error(f"Error tracking category performance: {e}")
    
    def detect_model_drift(self) -> Dict[str, Any]:
        """Detect if model performance is degrading"""
        try:
            # Compare recent accuracy to baseline
            query = f"""
            WITH recent_accuracy AS (
                SELECT 
                    model_version,
                    ROUND(SUM(CASE WHEN original_category = user_category THEN 1 ELSE 0 END) / COUNT(*), 3) as recent_accuracy,
                    COUNT(*) as sample_size
                FROM `{self.project_id}.{self._get_dataset_id()}.ml_feedback`
                WHERE feedback_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
                GROUP BY model_version
            ),
            baseline_accuracy AS (
                SELECT 
                    model_version,
                    ROUND(SUM(CASE WHEN original_category = user_category THEN 1 ELSE 0 END) / COUNT(*), 3) as baseline_accuracy
                FROM `{self.project_id}.{self._get_dataset_id()}.ml_feedback`
                WHERE feedback_timestamp BETWEEN 
                    TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) AND
                    TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
                GROUP BY model_version
            )
            SELECT 
                r.model_version,
                r.recent_accuracy,
                b.baseline_accuracy,
                r.recent_accuracy - b.baseline_accuracy as accuracy_change,
                r.sample_size
            FROM recent_accuracy r
            JOIN baseline_accuracy b USING (model_version)
            """
            
            query_job = self.bigquery.query(query)
            results = list(query_job)
            
            drift_detected = False
            drift_details = []
            
            for row in results:
                if row.accuracy_change < -0.05:  # 5% degradation threshold
                    drift_detected = True
                    drift_details.append({
                        'model_version': row.model_version,
                        'recent_accuracy': float(row.recent_accuracy),
                        'baseline_accuracy': float(row.baseline_accuracy),
                        'accuracy_change': float(row.accuracy_change),
                        'sample_size': row.sample_size
                    })
                    
                    # Write alert metric
                    self.write_model_metric("model_drift_detected", 1.0, 
                                          {"model_version": row.model_version})
            
            return {
                'drift_detected': drift_detected,
                'details': drift_details,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting model drift: {e}")
            return {'drift_detected': False, 'error': str(e)}
    
    def create_monitoring_dashboard(self):
        """Create a Cloud Monitoring dashboard for ML metrics"""
        try:
            dashboard_config = {
                "displayName": "ML Model Performance Dashboard",
                "gridLayout": {
                    "widgets": [
                        self._create_accuracy_widget(),
                        self._create_predictions_widget(),
                        self._create_confidence_widget(),
                        self._create_feedback_widget(),
                        self._create_category_distribution_widget(),
                        self._create_drift_alert_widget()
                    ]
                }
            }
            
            dashboard = v1.Dashboard(dashboard_config)
            created = self.dashboard_client.create_dashboard(
                parent=self.project_path,
                dashboard=dashboard
            )
            
            self.logger.info(f"Created dashboard: {created.name}")
            return created.name
            
        except Exception as e:
            self.logger.error(f"Error creating dashboard: {e}")
            return None
    
    def _create_accuracy_widget(self) -> Dict[str, Any]:
        """Create accuracy tracking widget"""
        return {
            "title": "Model Accuracy",
            "xyChart": {
                "dataSets": [{
                    "timeSeriesQuery": {
                        "timeSeriesFilter": {
                            "filter": f'metric.type="{self.metric_type_prefix}/accuracy"',
                            "aggregation": {
                                "alignmentPeriod": "3600s",
                                "perSeriesAligner": "ALIGN_MEAN"
                            }
                        }
                    },
                    "plotType": "LINE"
                }]
            }
        }
    
    def _create_predictions_widget(self) -> Dict[str, Any]:
        """Create predictions volume widget"""
        return {
            "title": "Predictions per Hour",
            "xyChart": {
                "dataSets": [{
                    "timeSeriesQuery": {
                        "timeSeriesFilter": {
                            "filter": f'metric.type="{self.metric_type_prefix}/predictions_per_hour"',
                            "aggregation": {
                                "alignmentPeriod": "3600s",
                                "perSeriesAligner": "ALIGN_SUM"
                            }
                        }
                    },
                    "plotType": "STACKED_BAR"
                }]
            }
        }
    
    def _create_confidence_widget(self) -> Dict[str, Any]:
        """Create confidence tracking widget"""
        return {
            "title": "Average Prediction Confidence",
            "xyChart": {
                "dataSets": [{
                    "timeSeriesQuery": {
                        "timeSeriesFilter": {
                            "filter": f'metric.type="{self.metric_type_prefix}/avg_confidence"',
                            "aggregation": {
                                "alignmentPeriod": "3600s",
                                "perSeriesAligner": "ALIGN_MEAN"
                            }
                        }
                    },
                    "plotType": "LINE"
                }],
                "yAxis": {
                    "scale": "LINEAR",
                    "label": "Confidence Score"
                }
            }
        }
    
    def _create_feedback_widget(self) -> Dict[str, Any]:
        """Create feedback tracking widget"""
        return {
            "title": "User Feedback Count",
            "xyChart": {
                "dataSets": [{
                    "timeSeriesQuery": {
                        "timeSeriesFilter": {
                            "filter": f'metric.type="{self.metric_type_prefix}/feedback_count"',
                            "aggregation": {
                                "alignmentPeriod": "86400s",
                                "perSeriesAligner": "ALIGN_SUM"
                            }
                        }
                    },
                    "plotType": "STACKED_BAR"
                }]
            }
        }
    
    def _create_category_distribution_widget(self) -> Dict[str, Any]:
        """Create category distribution widget"""
        return {
            "title": "Category Distribution",
            "xyChart": {
                "dataSets": [{
                    "timeSeriesQuery": {
                        "timeSeriesFilter": {
                            "filter": f'metric.type="{self.metric_type_prefix}/category_predictions"',
                            "aggregation": {
                                "alignmentPeriod": "3600s",
                                "perSeriesAligner": "ALIGN_SUM",
                                "groupByFields": ["metric.label.category"]
                            }
                        }
                    },
                    "plotType": "STACKED_BAR"
                }]
            }
        }
    
    def _create_drift_alert_widget(self) -> Dict[str, Any]:
        """Create model drift alert widget"""
        return {
            "title": "Model Drift Detection",
            "scorecard": {
                "timeSeriesQuery": {
                    "timeSeriesFilter": {
                        "filter": f'metric.type="{self.metric_type_prefix}/model_drift_detected"',
                        "aggregation": {
                            "alignmentPeriod": "3600s",
                            "perSeriesAligner": "ALIGN_MAX"
                        }
                    }
                },
                "thresholds": [
                    {"value": 0.5, "color": "YELLOW"},
                    {"value": 1.0, "color": "RED"}
                ]
            }
        }
    
    def _get_dataset_id(self) -> str:
        """Get BigQuery dataset ID"""
        return f"{self.project_id.replace('-', '_')}_transactions"
    
    def run_monitoring_cycle(self):
        """Run a complete monitoring cycle"""
        self.logger.info("Starting monitoring cycle")
        
        # Track various metrics
        self.track_prediction_metrics()
        self.track_feedback_metrics()
        self.track_category_performance()
        
        # Check for model drift
        drift_result = self.detect_model_drift()
        if drift_result['drift_detected']:
            self.logger.warning(f"Model drift detected: {drift_result}")
            # Could trigger alerts or retraining here
        
        self.logger.info("Monitoring cycle complete") 