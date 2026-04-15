import pytest
import boto3
import sys
import os
import importlib
from moto import mock_aws

# adiciona raiz do projeto no path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


lambda_module = importlib.import_module("lambda.lambda_function")
lambda_handler = lambda_module.lambda_handler


# ---------------- FIXTURE AWS ----------------
@pytest.fixture(scope="function")
def aws_env():
    with mock_aws():
        # S3
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="meu-bucket")

        # DynamoDB
        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName="ControleProcessamentoV2",
            KeySchema=[{"AttributeName": "idRegistro", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "idRegistro", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST"
        )

        yield s3


# ---------------- TESTE 1 ----------------
def test_arquivo_nao_csv():
    event = {
        "bucket": {"name": "meu-bucket"},
        "object": {"key": "arquivo.txt"}
    }

    response = lambda_handler(event, None)

    assert response["status"] == "ERRO_ARQUIVO"


# ---------------- TESTE 2 ----------------
def test_processamento_sucesso(aws_env):
    csv_valido = """idRegistro,nomeProduto,satisfacaoCliente,quantidade
1,Produto A,5,10
"""

    aws_env.put_object(
        Bucket="meu-bucket",
        Key="arquivo.csv",
        Body=csv_valido
    )

    event = {
        "bucket": {"name": "meu-bucket"},
        "object": {"key": "arquivo.csv"}
    }

    response = lambda_handler(event, None)

    assert response["status"] == "PROCESSADO"


# ---------------- TESTE 3 ----------------
def test_processamento_erro(aws_env):
    csv_erro = """idRegistro,nomeProduto,satisfacaoCliente,quantidade
1,,10,0
"""

    aws_env.put_object(
        Bucket="meu-bucket",
        Key="arquivo.csv",
        Body=csv_erro
    )

    event = {
        "bucket": {"name": "meu-bucket"},
        "object": {"key": "arquivo.csv"}
    }

    response = lambda_handler(event, None)

    assert response["status"] == "PENDENTE_CORRECAO"


# ---------------- TESTE 4 ----------------
def test_eventbridge(aws_env):
    csv_valido = """idRegistro,nomeProduto,satisfacaoCliente,quantidade
1,Produto A,5,10
"""

    aws_env.put_object(
        Bucket="meu-bucket",
        Key="arquivo.csv",
        Body=csv_valido
    )

    event = {
        "detail": {
            "bucket": {"name": "meu-bucket"},
            "object": {"key": "arquivo.csv"}
        }
    }

    response = lambda_handler(event, None)

    assert response["status"] == "PROCESSADO"


# ---------------- TESTE 5 (DYNAMO) ----------------
def test_valida_dynamo(aws_env):
    csv_valido = """idRegistro,nomeProduto,satisfacaoCliente,quantidade
1,Produto A,5,10
"""

    aws_env.put_object(
        Bucket="meu-bucket",
        Key="arquivo.csv",
        Body=csv_valido
    )

    event = {
        "bucket": {"name": "meu-bucket"},
        "object": {"key": "arquivo.csv"}
    }

    lambda_handler(event, None)

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    tabela = dynamodb.Table("ControleProcessamentoV2")

    response = tabela.get_item(Key={"idRegistro": 1})

    assert response["Item"]["status"] == "PROCESSADO"


# ---------------- TESTE 6 (STEP FUNCTION - SUCESSO) ----------------
def test_step_function_sucesso(aws_env):
    csv_valido = """idRegistro,nomeProduto,satisfacaoCliente,quantidade
1,Produto A,5,10
"""

    aws_env.put_object(
        Bucket="meu-bucket",
        Key="arquivo.csv",
        Body=csv_valido
    )

    event = {
        "detail": {
            "bucket": {"name": "meu-bucket"},
            "object": {"key": "arquivo.csv"}
        }
    }

    response = lambda_handler(event, None)

    
    resultado = "SUCESSO" if response["status"] == "PROCESSADO" else "ERRO"

    assert resultado == "SUCESSO"


# ---------------- TESTE 7 (STEP FUNCTION - ERRO) ----------------
def test_step_function_erro(aws_env):
    csv_erro = """idRegistro,nomeProduto,satisfacaoCliente,quantidade
1,,10,0
"""

    aws_env.put_object(
        Bucket="meu-bucket",
        Key="arquivo.csv",
        Body=csv_erro
    )

    event = {
        "detail": {
            "bucket": {"name": "meu-bucket"},
            "object": {"key": "arquivo.csv"}
        }
    }

    response = lambda_handler(event, None)

    resultado = "SUCESSO" if response["status"] == "PROCESSADO" else "ERRO"

    assert resultado == "ERRO"