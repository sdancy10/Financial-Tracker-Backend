import os
import yaml
from typing import Any, Dict, Optional

class Config:
    """Configuration singleton for accessing config.yaml"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if not isinstance(cls._instance, cls):
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _process_placeholders(self, value: Any) -> Any:
        """Replace placeholders in configuration values"""
        if isinstance(value, str):
            # Replace project ID placeholder
            if '%PROJECT_ID%' in value:
                project_id = self._config.get('project', {}).get('id')
                if project_id:
                    value = value.replace('%PROJECT_ID%', project_id)
            
            # Replace tier placeholder
            if '%PROJECT_TIER%' in value:
                use_free_tier = self._config.get('project', {}).get('use_free_tier', False)
                tier = 'free_tier' if use_free_tier else 'standard'
                value = value.replace('%PROJECT_TIER%', tier)
            
            return value
        elif isinstance(value, dict):
            return {k: self._process_placeholders(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._process_placeholders(item) for item in value]
        return value
    
    def _load_config(self):
        """Load configuration from YAML file"""
        if self._config is None:
            config_path = os.getenv('CONFIG_PATH', 'config.yaml')
            try:
                with open(config_path, 'r') as f:
                    self._config = yaml.safe_load(f)
                # Process placeholders after loading but before first use
                self._config = self._process_placeholders(self._config)
            except Exception as e:
                print(f"Error loading config: {str(e)}")
                self._config = {}
    
    def get(self, *args: str, default: Any = None) -> Any:
        """Get a configuration value by path"""
        try:
            current = self._config
            for arg in args:
                if isinstance(current, dict) and arg in current:
                    current = current[arg]
                else:
                    return default
            return current
        except Exception:
            return default
    
    @classmethod
    def reset(cls):
        """Reset the singleton instance (for testing)"""
        cls._instance = None
        cls._config = None
    
    @classmethod
    def set_config(cls, config: Dict):
        """Set the configuration directly (for testing)"""
        if not isinstance(cls._instance, cls):
            cls._instance = super(Config, cls).__new__(cls)
        cls._instance._config = config 