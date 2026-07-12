from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.aws.awsService import AwsService


class DynamoDbService:
    def __init__(self, awsService: AwsService | None = None) -> None:
        self.awsService = awsService or AwsService()

    def putItem(self, tableName: str, item: dict[str, Any], conditionExpression: Any | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"Item": item}
        if conditionExpression is not None:
            kwargs["ConditionExpression"] = conditionExpression
        return self.awsService.dynamoTable(tableName).put_item(**kwargs)

    def getItem(self, tableName: str, key: dict[str, Any], consistentRead: bool = False) -> dict[str, Any] | None:
        response = self.awsService.dynamoTable(tableName).get_item(Key=key, ConsistentRead=consistentRead)
        item = response.get("Item")
        return item if isinstance(item, dict) else None

    def updateItem(
        self,
        tableName: str,
        key: dict[str, Any],
        updateExpression: str,
        expressionValues: dict[str, Any],
        expressionNames: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "Key": key,
            "UpdateExpression": updateExpression,
            "ExpressionAttributeValues": expressionValues,
            "ReturnValues": "ALL_NEW",
        }
        if expressionNames:
            kwargs["ExpressionAttributeNames"] = expressionNames
        return self.awsService.dynamoTable(tableName).update_item(**kwargs).get("Attributes", {})

    def queryByPk(
        self,
        tableName: str,
        pkValue: str,
        skBeginsWith: str = "",
        limit: int = 100,
        scanForward: bool = False,
    ) -> list[dict[str, Any]]:
        condition = Key("pk").eq(pkValue)
        if skBeginsWith:
            condition = condition & Key("sk").begins_with(skBeginsWith)
        response = self.awsService.dynamoTable(tableName).query(
            KeyConditionExpression=condition,
            ScanIndexForward=scanForward,
            Limit=max(1, min(limit, 500)),
        )
        return list(response.get("Items", []))

    def queryIndex(
        self,
        tableName: str,
        indexName: str,
        keyName: str,
        keyValue: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        response = self.awsService.dynamoTable(tableName).query(
            IndexName=indexName,
            KeyConditionExpression=Key(keyName).eq(keyValue),
            ScanIndexForward=False,
            Limit=max(1, min(limit, 100)),
        )
        return list(response.get("Items", []))

    def deleteItem(self, tableName: str, key: dict[str, Any]) -> None:
        self.awsService.dynamoTable(tableName).delete_item(Key=key)
