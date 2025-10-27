# /data/inception/app/config/agentops_config.py
import os
try:
    from agentops import init as _agentops_init
except Exception:
    _agentops_init = None

def init_agentops():
    key = os.environ.get("AGENTOPS_API_KEY")
    if not key:
        # Try SSM (if on EC2 with role) - Uses IAM role for S3/SSM access on EC2
        try:
            import boto3, botocore
            ssm = boto3.client("ssm", region_name=os.getenv("AWS_REGION", ""))
            param = ssm.get_parameter(Name="/inception/agentops_api_key", WithDecryption=True)
            key = param["Parameter"]["Value"]
        except Exception:
            key = None

    if not key:
        print("AgentOps key not found in env or SSM; AgentOps disabled")
        return None
    if _agentops_init:
        _agentops_init(api_key=key)
        print("AgentOps initialized")
    return key

