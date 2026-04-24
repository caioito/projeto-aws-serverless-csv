import pytest
import boto3
import json
import logging
from botocore.exceptions import ClientError

# Configurar logger
logger = logging.getLogger(__name__)

# ---------------- CONSTANTES ----------------
AWS_REGION = "us-east-1"
BUCKET_NAME = "projeto-processamento-arquivos"
TABLE_NAME = "ControleProcessamentoV2"
LAMBDA_NAME = "lambda-processar-csv"
STATE_MACHINE_NAME = "FluxoCSV"
EVENT_RULE_NAME = "regra-upload-s3-stepfunction"


# ---------------- CLIENTES AWS ----------------
@pytest.fixture(scope="module")
def aws_region():
    return AWS_REGION


@pytest.fixture(scope="module")
def s3_client(aws_region):
    return boto3.client("s3", region_name=aws_region)


@pytest.fixture(scope="module")
def dynamodb_client(aws_region):
    return boto3.client("dynamodb", region_name=aws_region)


@pytest.fixture(scope="module")
def lambda_client(aws_region):
    return boto3.client("lambda", region_name=aws_region)


@pytest.fixture(scope="module")
def sfn_client(aws_region):
    return boto3.client("stepfunctions", region_name=aws_region)


@pytest.fixture(scope="module")
def events_client(aws_region):
    return boto3.client("events", region_name=aws_region)


@pytest.fixture(scope="module")
def iam_client(aws_region):
    return boto3.client("iam", region_name=aws_region)


# ---------------- CACHE DOS RECURSOS ----------------
@pytest.fixture(scope="module")
def lambda_response(lambda_client):
    return lambda_client.get_function(FunctionName=LAMBDA_NAME)


@pytest.fixture(scope="module")
def dynamodb_response(dynamodb_client):
    return dynamodb_client.describe_table(TableName=TABLE_NAME)


@pytest.fixture(scope="module")
def state_machine_response(sfn_client):
    machines = sfn_client.list_state_machines()["stateMachines"]
    machine = next(sm for sm in machines if sm["name"] == STATE_MACHINE_NAME)

    response = sfn_client.describe_state_machine(
        stateMachineArn=machine["stateMachineArn"]
    )
    response["definition_json"] = json.loads(response["definition"])
    return response


@pytest.fixture(scope="module")
def event_rule_response(events_client):
    return events_client.describe_rule(Name=EVENT_RULE_NAME)


# ---------------- TESTES S3 ----------------
class TestS3Bucket:

    def test_bucket_exists(self, s3_client):
        response = s3_client.list_buckets()
        buckets = [bucket["Name"] for bucket in response["Buckets"]]

        assert BUCKET_NAME in buckets

    def test_bucket_eventbridge_enabled(self, s3_client):
        response = s3_client.get_bucket_notification_configuration(Bucket=BUCKET_NAME)

        assert "EventBridgeConfiguration" in response

    def test_bucket_region(self, s3_client, aws_region):
        response = s3_client.get_bucket_location(Bucket=BUCKET_NAME)
        location = response["LocationConstraint"] or "us-east-1"

        assert location == aws_region


# ---------------- TESTES DYNAMODB ----------------
class TestDynamoDB:

    def test_table_exists(self, dynamodb_response):
        assert dynamodb_response["Table"]["TableName"] == TABLE_NAME

    def test_table_configuration(self, dynamodb_response):
        table = dynamodb_response["Table"]

        assert table["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"
        assert table["KeySchema"][0]["AttributeName"] == "idRegistro"
        assert table["KeySchema"][0]["KeyType"] == "HASH"

    def test_table_attribute_type(self, dynamodb_response):
        attributes = dynamodb_response["Table"]["AttributeDefinitions"]

        id_attr = next(attr for attr in attributes if attr["AttributeName"] == "idRegistro")

        assert id_attr["AttributeType"] == "N"

    def test_table_status(self, dynamodb_response):
        assert dynamodb_response["Table"]["TableStatus"] == "ACTIVE"


# ---------------- TESTES LAMBDA ----------------
class TestLambdaFunction:

    def test_lambda_exists(self, lambda_response):
        assert lambda_response["Configuration"]["FunctionName"] == LAMBDA_NAME

    def test_lambda_runtime(self, lambda_response):
        assert lambda_response["Configuration"]["Runtime"] == "python3.10"

    def test_lambda_handler(self, lambda_response):
        assert lambda_response["Configuration"]["Handler"] == "lambda_function.lambda_handler"

    def test_lambda_role(self, lambda_response):
        role_arn = lambda_response["Configuration"]["Role"]
        assert "lambda-role-csv" in role_arn

    def test_lambda_timeout(self, lambda_response):
        timeout = lambda_response["Configuration"]["Timeout"]
        assert timeout >= 3


# ---------------- TESTES IAM ----------------
class TestIAMRoles:

    def test_lambda_role_exists(self, iam_client):
        response = iam_client.get_role(RoleName="lambda-role-csv")
        assert response["Role"]["RoleName"] == "lambda-role-csv"

    def test_lambda_role_policies(self, iam_client):
        response = iam_client.list_attached_role_policies(RoleName="lambda-role-csv")
        policies = [p["PolicyName"] for p in response["AttachedPolicies"]]

        assert "AWSLambdaBasicExecutionRole" in policies
        assert "AmazonS3FullAccess" in policies
        assert "AmazonDynamoDBFullAccess" in policies

    def test_step_function_role_exists(self, iam_client):
        response = iam_client.get_role(RoleName="step-role-csv")
        assert response["Role"]["RoleName"] == "step-role-csv"

    def test_eventbridge_role_exists(self, iam_client):
        response = iam_client.get_role(RoleName="eventbridge-step-role")
        assert response["Role"]["RoleName"] == "eventbridge-step-role"


# ---------------- TESTES STEP FUNCTION ----------------
class TestStepFunction:

    def test_state_machine_exists(self, state_machine_response):
        assert state_machine_response["name"] == STATE_MACHINE_NAME

    def test_state_machine_status(self, state_machine_response):
        assert state_machine_response["type"] == "STANDARD"

    def test_state_machine_definition(self, state_machine_response):
        definition = state_machine_response["definition_json"]

        assert definition["StartAt"] == "ProcessarArquivo"
        assert "ProcessarArquivo" in definition["States"]
        assert "VerificarStatus" in definition["States"]
        assert "Sucesso" in definition["States"]
        assert "Erro" in definition["States"]

    def test_state_machine_has_lambda_resource(self, state_machine_response, lambda_response):
        lambda_arn = lambda_response["Configuration"]["FunctionArn"]
        step_lambda_arn = state_machine_response["definition_json"]["States"]["ProcessarArquivo"]["Resource"]

        assert step_lambda_arn == lambda_arn


# ---------------- TESTES EVENTBRIDGE ----------------
class TestEventBridge:

    def test_event_rule_exists(self, event_rule_response):
        assert event_rule_response["Name"] == EVENT_RULE_NAME

    def test_event_rule_pattern(self, event_rule_response):
        pattern = json.loads(event_rule_response["EventPattern"])

        assert "aws.s3" in pattern["source"]
        assert "Object Created" in pattern["detail-type"]

    def test_event_rule_state(self, event_rule_response):
        assert event_rule_response["State"] == "ENABLED"

    def test_event_rule_target(self, events_client, state_machine_response):
        response = events_client.list_targets_by_rule(Rule=EVENT_RULE_NAME)
        targets = response["Targets"]

        assert len(targets) > 0
        assert targets[0]["Arn"] == state_machine_response["stateMachineArn"]


# ---------------- TESTE INTEGRAÇÃO ----------------
class TestIntegration:

    def test_complete_workflow_resources(self, s3_client, lambda_response,
                                         dynamodb_response, state_machine_response,
                                         event_rule_response):

        s3_client.head_bucket(Bucket=BUCKET_NAME)

        assert lambda_response["Configuration"]["FunctionName"] == LAMBDA_NAME
        assert dynamodb_response["Table"]["TableName"] == TABLE_NAME
        assert state_machine_response["name"] == STATE_MACHINE_NAME
        assert event_rule_response["Name"] == EVENT_RULE_NAME