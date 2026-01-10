import os
import urllib.request
import boto3
from fastapi import APIRouter

router = APIRouter()

GOOGLE_METADATA_IDENTITY_URL = (
    "http://metadata/computeMetadata/v1/instance/service-accounts/default/identity"
)


def fetch_google_id_token(audience: str) -> str:
    url = f"{GOOGLE_METADATA_IDENTITY_URL}?audience={audience}&format=full"
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode()


@router.get("/debug/aws-wif")
def debug_aws_wif():
    region = os.getenv("AWS_REGION")
    role_arn = os.getenv("AWS_ROLE_ARN")
    audience = os.getenv("AWS_OIDC_AUDIENCE")

    token = fetch_google_id_token(audience)

    sts = boto3.client("sts", region_name=region)
    creds = sts.assume_role_with_web_identity(
        RoleArn=role_arn,
        RoleSessionName="aether-cloudrun",
        WebIdentityToken=token,
        DurationSeconds=3600,
    )["Credentials"]

    sts2 = boto3.client(
        "sts",
        region_name=region,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )

    return sts2.get_caller_identity()
