provider "aws" {
  region = var.aws_region
}

# ========================
# S3
# ========================
resource "aws_s3_bucket" "bucket" {
  bucket = "projeto-csv-${var.environment}"

  lifecycle {
    prevent_destroy = var.destroyer == false
  }
}

resource "aws_s3_bucket_notification" "eventbridge" {
  bucket      = aws_s3_bucket.bucket.id
  eventbridge = true
}

# ========================
# DYNAMODB
# ========================
resource "aws_dynamodb_table" "tabela" {
  name         = "ControleProcessamento-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idRegistro"

  attribute {
    name = "idRegistro"
    type = "N"
  }

  lifecycle {
    prevent_destroy = var.destroyer == false
  }
}

# ========================
# IAM LAMBDA
# ========================
resource "aws_iam_role" "lambda_role" {
  name = "lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_s3" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "lambda_dynamo" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

# ========================
# LAMBDA ZIP
# ========================
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda"
  output_path = "${path.module}/lambda.zip"
}

# ========================
# LAMBDA
# ========================
resource "aws_lambda_function" "lambda" {
  function_name = "lambda-processar-${var.environment}"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
}

# ========================
# IAM STEP FUNCTION
# ========================
resource "aws_iam_role" "step_role" {
  name = "step-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "states.amazonaws.com" },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "step_lambda" {
  role = aws_iam_role.step_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Action = "lambda:InvokeFunction",
      Resource = aws_lambda_function.lambda.arn
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge_policy" {
  role = aws_iam_role.step_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Action = "states:StartExecution",
      Resource = aws_sfn_state_machine.step.arn
    }]
  })
}

# ========================
# STEP FUNCTION
# ========================
resource "aws_sfn_state_machine" "step" {
  name     = "FluxoCSV-${var.environment}"
  role_arn = aws_iam_role.step_role.arn

  definition = jsonencode({
    StartAt = "ProcessarArquivo",
    States = {
      ProcessarArquivo = {
        Type     = "Task",
        Resource = aws_lambda_function.lambda.arn,
        Next     = "VerificarStatus"
      },
      VerificarStatus = {
        Type = "Choice",
        Choices = [
          {
            Variable     = "$.status",
            StringEquals = "PROCESSADO",
            Next         = "Sucesso"
          },
          {
            Variable     = "$.status",
            StringEquals = "PENDENTE_CORRECAO",
            Next         = "Erro"
          }
        ]
      },
      Sucesso = { Type = "Succeed" },
      Erro    = { Type = "Fail" }
    }
  })
}

# ========================
# EVENTBRIDGE
# ========================
resource "aws_cloudwatch_event_rule" "s3_event" {
  name = "regra-upload-${var.environment}"

  event_pattern = jsonencode({
    source      = ["aws.s3"],
    detail-type = ["Object Created"],
    detail = {
      bucket = {
        name = [aws_s3_bucket.bucket.bucket]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "step_target" {
  rule      = aws_cloudwatch_event_rule.s3_event.name
  target_id = "StepFunction"
  arn       = aws_sfn_state_machine.step.arn
  role_arn  = aws_iam_role.step_role.arn
}