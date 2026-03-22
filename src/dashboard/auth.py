"""
Módulo de autenticação para o Dashboard de Crédito.

Gerencia login, registro de novos usuários e painel de aprovação admin.
Usa streamlit-authenticator + YAML para persistência.
"""

import os
import yaml
import bcrypt
import streamlit as st
from datetime import datetime

# Caminhos dos arquivos de usuários
AUTH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
USERS_FILE = os.path.join(AUTH_DIR, "users.yaml")
PENDING_FILE = os.path.join(AUTH_DIR, "pending_users.yaml")


def _load_yaml(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_yaml(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _ensure_users_file():
    """Cria o arquivo de usuários com o admin padrão se não existir."""
    if not os.path.exists(USERS_FILE):
        admin_data = {
            "users": {
                "admin": {
                    "name": "Administrador",
                    "email": "admin@dashboard.com",
                    "password": _hash_password("admin123"),
                    "role": "admin",
                    "approved": True,
                }
            },
            "cookie": {
                "name": "dashboard_credito_auth",
                "key": "dashboard_credito_secret_key_2026",
                "expiry_days": 30,
            },
        }
        _save_yaml(USERS_FILE, admin_data)


def _ensure_pending_file():
    if not os.path.exists(PENDING_FILE):
        _save_yaml(PENDING_FILE, {"pending": []})


def show_login() -> tuple[bool, str, str]:
    """
    Exibe formulário de login.

    Returns:
        (authenticated, username, role)
    """
    _ensure_users_file()

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["username"] = ""
        st.session_state["user_role"] = ""

    if st.session_state["authenticated"]:
        return True, st.session_state["username"], st.session_state["user_role"]

    users_data = _load_yaml(USERS_FILE)
    users = users_data.get("users", {})

    st.markdown("### Login")
    username = st.text_input("Usuário", key="login_username")
    password = st.text_input("Senha", type="password", key="login_password")

    if st.button("Entrar", key="login_btn"):
        if username in users:
            user = users[username]
            if user.get("approved", False) and _check_password(password, user["password"]):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.session_state["user_role"] = user.get("role", "viewer")
                st.rerun()
            elif not user.get("approved", False):
                st.error("Sua conta ainda aguarda aprovação do administrador.")
            else:
                st.error("Usuário ou senha incorretos.")
        else:
            st.error("Usuário ou senha incorretos.")

    return False, "", ""


def show_registration_form():
    """Exibe formulário de registro (solicitação de conta)."""
    _ensure_pending_file()

    st.markdown("### Solicitar Acesso")
    st.info("Preencha o formulário abaixo. Sua solicitação será enviada ao administrador para aprovação.")

    with st.form("registration_form", clear_on_submit=True):
        name = st.text_input("Nome completo")
        email = st.text_input("Email")
        username = st.text_input("Nome de usuário (para login)")
        password = st.text_input("Senha", type="password")
        password_confirm = st.text_input("Confirmar senha", type="password")

        submitted = st.form_submit_button("Solicitar cadastro")

        if submitted:
            if not all([name, email, username, password, password_confirm]):
                st.error("Preencha todos os campos.")
                return

            if password != password_confirm:
                st.error("As senhas não coincidem.")
                return

            if len(password) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
                return

            # Verificar se username já existe
            users_data = _load_yaml(USERS_FILE)
            if username in users_data.get("users", {}):
                st.error("Este nome de usuário já está em uso.")
                return

            # Verificar se já tem solicitação pendente
            pending_data = _load_yaml(PENDING_FILE)
            pending_list = pending_data.get("pending", [])
            if any(p["username"] == username for p in pending_list):
                st.warning("Já existe uma solicitação pendente com este nome de usuário.")
                return

            # Adicionar à lista de pendentes
            pending_list.append({
                "username": username,
                "name": name,
                "email": email,
                "password": _hash_password(password),
                "requested_at": datetime.now().isoformat(),
            })
            pending_data["pending"] = pending_list
            _save_yaml(PENDING_FILE, pending_data)
            st.success("Solicitação enviada! Aguarde a aprovação do administrador.")


def show_admin_panel():
    """Painel de aprovação de usuários (apenas para admin)."""
    _ensure_pending_file()

    pending_data = _load_yaml(PENDING_FILE)
    pending_list = pending_data.get("pending", [])

    users_data = _load_yaml(USERS_FILE)
    users = users_data.get("users", {})

    with st.sidebar.expander(f"Admin — Usuários ({len(pending_list)} pendentes)", expanded=False):
        # Usuários aprovados
        st.markdown("**Usuários ativos:**")
        for uname, udata in users.items():
            role_badge = "admin" if udata.get("role") == "admin" else "viewer"
            st.markdown(f"- `{uname}` ({udata.get('name', '')}) — {role_badge}")

        st.markdown("---")

        # Solicitações pendentes
        if pending_list:
            st.markdown("**Solicitações pendentes:**")
            for idx, pending in enumerate(pending_list):
                st.markdown(
                    f"**{pending['name']}** (`{pending['username']}`)\n\n"
                    f"Email: {pending['email']}\n\n"
                    f"Solicitado em: {pending['requested_at'][:10]}"
                )
                col_approve, col_reject = st.columns(2)
                with col_approve:
                    if st.button("Aprovar", key=f"approve_{idx}"):
                        # Mover para users.yaml
                        users[pending["username"]] = {
                            "name": pending["name"],
                            "email": pending["email"],
                            "password": pending["password"],
                            "role": "viewer",
                            "approved": True,
                        }
                        users_data["users"] = users
                        _save_yaml(USERS_FILE, users_data)

                        # Remover de pendentes
                        pending_list.pop(idx)
                        pending_data["pending"] = pending_list
                        _save_yaml(PENDING_FILE, pending_data)
                        st.rerun()

                with col_reject:
                    if st.button("Rejeitar", key=f"reject_{idx}"):
                        pending_list.pop(idx)
                        pending_data["pending"] = pending_list
                        _save_yaml(PENDING_FILE, pending_data)
                        st.rerun()

                st.markdown("---")
        else:
            st.caption("Nenhuma solicitação pendente.")


def show_logout():
    """Botão de logout na sidebar."""
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"Logado como: **{st.session_state.get('username', '')}**")
        if st.button("Sair", key="logout_btn"):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.session_state["user_role"] = ""
            st.rerun()
