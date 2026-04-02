def lambda_handler(event, context):
    print("Evento recebido:", event)

    # suporta dois formatos
    if "detail" in event:
        bucket = event["detail"]["bucket"]["name"]
        arquivo = event["detail"]["object"]["key"]
    else:
        bucket = event["bucket"]["name"]
        arquivo = event["object"]["key"]