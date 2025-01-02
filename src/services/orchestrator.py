from google.cloud import functions_v2, run_v2
from google.cloud.functions_v2.types import Function
from google.cloud.run_v2.services.services import ServicesClient
from google.cloud.run_v2.types import Service
from typing import List
from dataclasses import dataclass, field
from src.utils.config import Config

@dataclass
class GCPOrchestrator:
    project_id: str
    region: str = "us-central1"
    jobs: List[dict] = field(default_factory=list)
    
    def __init__(self, project_id: str, region: str = "us-central1"):
        self.project_id = project_id
        self.region = region
        self.functions_client = functions_v2.FunctionServiceClient()
        self.run_client = run_v2.ServicesClient()

    def run(self) -> bool:
        """
        Deploys and executes all jobs in GCP
        """
        for job in self.jobs:
            if job["type"] == "function":
                self._deploy_function(job)
            elif job["type"] == "cloudrun":
                self._deploy_cloudrun(job)
        return True

    def add_job(self, job_config: dict) -> bool:
        """
        Adds a job configuration to be deployed to GCP
        :param job_config: Dictionary containing job configuration
        :return: bool indicating success
        """
        # Validate job config
        required_fields = ["type", "name", "source_code_path"]
        if not all(field in job_config for field in required_fields):
            raise ValueError(f"Job config must contain fields: {required_fields}")
            
        self.jobs.append(job_config)
        return True

    def _deploy_function(self, job_config: dict):
        # Implementation for Cloud Functions deployment
        parent = f"projects/{self.project_id}/locations/{self.region}"
        function = Function(
            name=f"{parent}/functions/{job_config['name']}",
            build_config={
                "runtime": "python310",
                "entry_point": job_config.get("entry_point", "main"),
                "source": {"storage_source": {"bucket": job_config["source_code_path"]}}
            }
        )
        operation = self.functions_client.create_function(
            request={"parent": parent, "function": function}
        )
        return operation.result()

    def _deploy_cloudrun(self, job_config: dict):
        # Implementation for Cloud Run deployment
        parent = f"projects/{self.project_id}/locations/{self.region}"
        service = Service(
            name=f"{parent}/services/{job_config['name']}",
            template={
                "containers": [{
                    "image": job_config["source_code_path"],
                }]
            }
        )
        operation = self.run_client.create_service(
            request={"parent": parent, "service": service, "service_id": job_config['name']}
        )
        return operation.result()

def main():
    config = Config()
    orchestrator = GCPOrchestrator(project_id=config.get('project', 'id'))
    
    function_job = {
        "type": "function",
        "name": config.get('cloud_function', 'name'),
        "source_code_path": config.get('cloud_function', 'source_path'),
        "entry_point": config.get('cloud_function', 'entry_point')
    }
    
    cloud_run_job = {
        "type": "cloudrun",
        "name": config.get('cloud_run', 'service_name'),
        "source_code_path": config.get('cloud_run', 'container_image')
    }
    
    orchestrator.add_job(function_job)
    orchestrator.add_job(cloud_run_job)
    orchestrator.run()

if __name__ == '__main__':
    main() 