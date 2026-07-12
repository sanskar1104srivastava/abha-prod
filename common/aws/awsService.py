from __future__ import annotations

import json
import os
from functools import cached_property
from typing import Any

import boto3

from common.config.settings import getSettings


class AwsService:
    """Single access point for boto3 clients and resources."""

    def __init__(self, awsRegion: str | None = None, awsProfile: str | None = None) -> None:
        if awsRegion is not None or awsProfile is not None:
            self.awsRegion = awsRegion or os.environ.get("AWS_REGION") or os.environ.get("awsRegion") or "ap-south-1"
            self.awsProfile = awsProfile if awsProfile is not None else os.environ.get("AWS_PROFILE", "")
        else:
            settings = getSettings()
            self.awsRegion = settings.awsRegion
            self.awsProfile = settings.awsProfile

    @cached_property
    def session(self):
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            return boto3.Session(region_name=self.awsRegion)
        if self.awsProfile:
            return boto3.Session(profile_name=self.awsProfile, region_name=self.awsRegion)
        return boto3.Session(region_name=self.awsRegion)

    def dynamoResource(self):
        return self.session.resource("dynamodb", region_name=self.awsRegion)

    def dynamoTable(self, tableName: str):
        return self.dynamoResource().Table(tableName)

    def sqsClient(self):
        return self.session.client("sqs", region_name=self.awsRegion)

    def s3Client(self):
        return self.session.client("s3", region_name=self.awsRegion)

    def lambdaClient(self):
        return self.session.client("lambda", region_name=self.awsRegion)

    def ecrClient(self):
        return self.session.client("ecr", region_name=self.awsRegion)

    def secretsManagerClient(self):
        return self.session.client("secretsmanager", region_name=self.awsRegion)

    def getSecretString(self, secretName: str) -> str:
        response = self.secretsManagerClient().get_secret_value(SecretId=secretName)
        return str(response.get("SecretString") or "")

    def sendQueueMessage(self, queueUrl: str, message: dict[str, Any]) -> dict[str, Any]:
        return self.sqsClient().send_message(
            QueueUrl=queueUrl,
            MessageBody=json.dumps(message, default=str, separators=(",", ":")),
        )

    def putJsonObject(self, bucket: str, key: str, body: dict[str, Any]) -> None:
        self.s3Client().put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(body, default=str, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )

    def getJsonObject(self, bucket: str, key: str) -> dict[str, Any]:
        response = self.s3Client().get_object(Bucket=bucket, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))

    def deleteObject(self, bucket: str, key: str) -> None:
        self.s3Client().delete_object(Bucket=bucket, Key=key)
