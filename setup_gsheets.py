"""
Script para configurar Google Sheets como backend de autenticação.

PASSO A PASSO:
1. Acesse https://console.cloud.google.com
2. Crie um projeto (ou use existente)
3. Ative as APIs: Google Sheets API e Google Drive API
4. Crie uma Service Account: IAM & Admin > Service Accounts > Create
5. Gere uma chave JSON e salve como 'service_account.json' nesta pasta
6. Execute este script: python setup_gsheets.py
7. O script cria a planilha e imprime a URL
8. Configure os secrets no Streamlit Cloud (veja instruções ao final)
"""

import json
import os
import sys

def main():
    # Verificar se o arquivo de credenciais existe
    cred_file = os.path.join(os.path.dirname(__file__), "service_account.json")
    if not os.path.exists(cred_file):
        print("=" * 60)
        print("ERRO: Arquivo 'service_account.json' não encontrado!")
        print()
        print("Siga os passos:")
        print("1. Acesse https://console.cloud.google.com")
        print("2. Crie/selecione um projeto")
        print("3. Ative: Google Sheets API e Google Drive API")
        print("4. Vá em IAM & Admin > Service Accounts")
        print("5. Crie uma Service Account")
        print("6. Em Keys > Add Key > JSON")
        print("7. Salve o arquivo como 'service_account.json' aqui:")
        print(f"   {cred_file}")
        print("8. Execute novamente: python setup_gsheets.py")
        print("=" * 60)
        return

    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        json.load(open(cred_file)), scopes=scopes
    )
    client = gspread.authorize(creds)

    # Criar planilha
    spreadsheet = client.create("Dashboard Credito - Usuarios")

    # Compartilhar com o próprio usuário (editar o email abaixo)
    # spreadsheet.share("seu_email@gmail.com", perm_type="user", role="writer")

    # Criar aba "users" com header + admin padrão
    ws_users = spreadsheet.sheet1
    ws_users.update_title("users")
    ws_users.append_row(["username", "name", "email", "password", "role", "approved"])

    import bcrypt
    admin_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
    ws_users.append_row(["admin", "Administrador", "admin@dashboard.com", admin_hash, "admin", "True"])

    # Criar aba "pending"
    ws_pending = spreadsheet.add_worksheet(title="pending", rows=100, cols=10)
    ws_pending.append_row(["username", "name", "email", "password", "requested_at"])

    print("=" * 60)
    print("PLANILHA CRIADA COM SUCESSO!")
    print(f"URL: {spreadsheet.url}")
    print(f"ID:  {spreadsheet.id}")
    print()
    print("Service Account email (compartilhe a planilha com este email):")
    sa_email = json.load(open(cred_file)).get("client_email", "???")
    print(f"  {sa_email}")
    print()
    print("=" * 60)
    print()
    print("PRÓXIMOS PASSOS:")
    print()
    print("1. A planilha foi criada na conta da service account.")
    print(f"   Para acessá-la no seu Drive, compartilhe com seu email.")
    print()
    print("2. Configure os secrets no Streamlit Cloud:")
    print("   App Settings > Secrets, cole:")
    print()

    sa_data = json.load(open(cred_file))
    print("[gcp_service_account]")
    for key in ["type", "project_id", "private_key_id", "private_key",
                "client_email", "client_id", "auth_uri", "token_uri",
                "auth_provider_x509_cert_url", "client_x509_cert_url"]:
        val = sa_data.get(key, "")
        if "\n" in str(val):
            print(f'{key} = """{val}"""')
        else:
            print(f'{key} = "{val}"')

    print()
    print("[gsheets]")
    print(f'spreadsheet_url = "{spreadsheet.url}"')
    print()
    print("3. Também crie o arquivo .streamlit/secrets.toml local")
    print("   com o mesmo conteúdo (para testar localmente).")
    print("=" * 60)


if __name__ == "__main__":
    main()
