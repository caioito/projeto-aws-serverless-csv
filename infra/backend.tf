terraform {
  backend "s3" {
    # Nome do bucket S3 que vai armazenar o state
    bucket = "meu-backend-terraform"

    # Caminho do arquivo state dentro do bucket
    key = "state/terraform.tfstate"

    # Região AWS do bucket
    region = "us-east-1"
  }
}