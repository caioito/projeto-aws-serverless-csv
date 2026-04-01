import boto3
import csv
from datetime import datetime
from io import StringIO

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
tabela = dynamodb.Table('ControleProcessamentoV2')

def lambda_handler(event, context):
    print("Evento recebido:", event)

    
    if "detail" in event:
        bucket = event["detail"]["bucket"]["name"]
        arquivo = event["detail"]["object"]["key"]
    else:
        bucket = event["bucket"]["name"]
        arquivo = event["object"]["key"]

    # valida extensão
    if not arquivo.lower().endswith(".csv"):
        return {"status": "ERRO_ARQUIVO"}

    obj = s3.get_object(Bucket=bucket, Key=arquivo)
    conteudo = obj['Body'].read().decode('utf-8')
    reader = csv.DictReader(StringIO(conteudo))

    houve_erro = False

    for linha in reader:
        try:
            if (
                not linha['idRegistro'] or
                not linha['nomeProduto'] or not linha['nomeProduto'].strip() or
                not linha['satisfacaoCliente'] or
                not linha['quantidade']
            ):
                raise ValueError("Campos obrigatórios não preenchidos")

            id_registro = int(linha['idRegistro'])
            satisfacao = int(linha['satisfacaoCliente'])
            quantidade = int(linha['quantidade'])

            if satisfacao < 1 or satisfacao > 5:
                raise ValueError("Satisfação inválida")

            if quantidade <= 0:
                raise ValueError("Quantidade inválida")

            tabela.put_item(
                Item={
                    "idRegistro": id_registro,
                    "nomeProduto": linha['nomeProduto'].strip(),
                    "satisfacaoCliente": satisfacao,
                    "quantidade": quantidade,
                    "status": "PROCESSADO",
                    "dataProcessamento": datetime.now().isoformat()
                }
            )

        except Exception as e:
            houve_erro = True

            id_raw = str(linha.get('idRegistro', '')).strip()

            tabela.put_item(
                Item={
                    "idRegistro": int(id_raw) if id_raw.isdigit() else 0,
                    "nomeProduto": linha.get('nomeProduto', 'PREENCHER_MANUAL'),
                    "satisfacaoCliente": int(linha.get('satisfacaoCliente', 0)) if str(linha.get('satisfacaoCliente', '')).isdigit() else 0,
                    "quantidade": int(linha.get('quantidade', 0)) if str(linha.get('quantidade', '')).isdigit() else 0,
                    "status": "PENDENTE_CORRECAO",
                    "erro": str(e),
                    "dataProcessamento": datetime.now().isoformat()
                }
            )

    return {
        "status": "PENDENTE_CORRECAO" if houve_erro else "PROCESSADO"
    }