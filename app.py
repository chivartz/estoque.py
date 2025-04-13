#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import datetime
from datetime import timedelta
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file
)
from fpdf import FPDF

# ────────────────────────────── CONFIGURAÇÃO BÁSICA ──────────────────────────────
app = Flask(__name__)
app.secret_key = "minha_chave_secreta"  # Em produção, usar variável de ambiente
app.permanent_session_lifetime = timedelta(days=30)

# Arquivos de dados
USERS_FILE     = "usuarios.json"
STOCK_FILE     = "estoque.json"
LOGS_FILE      = "logs.json"
SUBSTOCK_FILE  = "subestoques.json"
CHAMADOS_FILE  = "chamados.json"   # Adicionado para chamados
CLIENTES_FILE  = "clientes.json"   # Adicionado para clientes

# ────────────────────────────── FUNÇÕES UTILITÁRIAS ──────────────────────────────
def load_data(file_path, default_factory=list):
    """Carrega dados JSON; se houver erro ou arquivo ausente, retorna valor padrão."""
    if not os.path.exists(file_path):
        return default_factory() if callable(default_factory) else default_factory
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_factory() if callable(default_factory) else default_factory

def save_data(file_path, data):
    """Salva dados no arquivo JSON com formatação legível."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def log_action(action, user):
    """Registra ação com timestamp e usuário no log."""
    logs = load_data(LOGS_FILE, list)
    logs.append({
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user,
        "action": action
    })
    save_data(LOGS_FILE, logs)

# ────────────────────────────── SESSÃO: AUTENTICAÇÃO E DASHBOARD ──────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        users = load_data(USERS_FILE, list)
        for user in users:
            if user["username"].lower() == username.lower() and user["password"] == password:
                session["username"] = user["username"]
                session["role"] = user["role"]
                session.permanent = True
                # Armazena dados de subestoque sempre que existirem
                if "sub_id" in user:
                    session["sub_id"] = user["sub_id"]
                    session["sub_nome"] = user.get("sub_nome", "")
                log_action("Login realizado", username)
                return redirect(url_for("dashboard"))
        flash("Credenciais inválidas. Verifique usuário e/ou senha.")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    """Exibe o dashboard após login."""
    if "username" not in session:
        flash("Faça login primeiro.")
        return redirect(url_for("login"))
    return render_template("dashboard.html", tipo=session.get("role"))

# ────────────────────────────── SESSÃO: ESTOQUE E SUBESTOQUES ──────────────────────────────
@app.route("/inventory")
def inventory():
    """
    Exibe o estoque principal ou o subestoque (para subusuário),
    permite filtrar por busca e itens críticos.
    """
    if "username" not in session:
        flash("Faça login para acessar o sistema.")
        return redirect(url_for("login"))

    # Usuário subusuário visualiza seu próprio subestoque
    if session.get("role") == "nv1":
        subs = load_data(SUBSTOCK_FILE, list)
        sub = next((s for s in subs if s["id"] == session.get("sub_id")), {})
        stock = sub.get("itens", [])
        subinventory_nome = sub.get("nome", "Meu Estoque")
    else:
        stock = load_data(STOCK_FILE, list)
        subinventory_nome = ""

    # Filtro por texto
    search_query = request.args.get("search", "").lower()
    if search_query:
        stock = [
            item for item in stock
            if search_query in item["nome"].lower()
            or search_query in item["codigo"].lower()
            or search_query in item.get("fabricante", "").lower()
            or search_query in item.get("tipo", "").lower()
        ]

    # Filtro por itens críticos
    critico = request.args.get("critico")
    if critico == "1":
        stock = [
            item for item in stock
            if item.get("nivel_critico") is not None
               and int(item["quantidade"]) <= int(item["nivel_critico"])
        ]

    suggestions = [i["nome"] for i in load_data(STOCK_FILE, list)]
    subinventories = load_data(SUBSTOCK_FILE, list)
    
    return render_template(
        "inventory.html",
        stock=stock,
        subinventory_nome=subinventory_nome,
        suggestions=suggestions,
        subinventories=subinventories
    )

@app.route("/add_inventory", methods=["POST"])
def add_inventory():
    """Adiciona ou atualiza item no estoque principal (não permitido para subusuário)."""
    if "username" not in session or session["role"] == "nv1":
        flash("Ação não autorizada.")
        return redirect(url_for("inventory"))

    nome = request.form.get("nome", "").strip()
    tipo = request.form.get("tipo")
    try:
        quantidade = int(request.form.get("quantidade"))
    except ValueError:
        flash("Quantidade inválida.")
        return redirect(url_for("inventory"))

    fabricante = request.form.get("fabricante", "").strip()
    voltagem = request.form.get("voltagem", "").strip()
    if voltagem and not voltagem.lower().endswith("v"):
        voltagem += "v"
    nc = request.form.get("nivel_critico")
    nivel_critico = int(nc) if (nc and nc.isdigit()) else None

    stock = load_data(STOCK_FILE, list)
    # Se o item já existe, soma a quantidade
    for item in stock:
        if item["nome"].strip().lower() == nome.lower() and item["tipo"] == tipo:
            item["quantidade"] += quantidade
            if fabricante:
                item["fabricante"] = fabricante
            if voltagem:
                item["voltagem"] = voltagem
            if nivel_critico is not None:
                item["nivel_critico"] = nivel_critico
            save_data(STOCK_FILE, stock)
            log_action(f"Atualizou item '{nome}' (+{quantidade})", session["username"])
            flash("Quantidade atualizada com sucesso!")
            return redirect(url_for("inventory"))

    # Cria novo item se não encontrado
    max_code = max((int(i["codigo"]) for i in stock), default=0)
    novo_codigo = str(max_code + 1).zfill(8)
    novo_item = {
        "codigo": novo_codigo,
        "nome": nome,
        "tipo": tipo,
        "quantidade": quantidade,
        "fabricante": fabricante,
        "voltagem": voltagem,
        "nivel_critico": nivel_critico
    }
    stock.append(novo_item)
    save_data(STOCK_FILE, stock)
    log_action(f"Adicionou novo item '{nome}'", session["username"])
    flash("Item adicionado com sucesso!")
    return redirect(url_for("inventory"))

@app.route("/withdraw_inventory", methods=["POST"])
def withdraw_inventory():
    """Retira quantidade de item do estoque principal (não permitido para subusuário)."""
    if "username" not in session or session["role"] == "nv1":
        flash("Ação não autorizada.")
        return redirect(url_for("inventory"))

    codigo = request.form.get("codigo", "")
    try:
        qtd = int(request.form.get("quantidade"))
    except ValueError:
        flash("Quantidade inválida.")
        return redirect(url_for("inventory"))

    stock = load_data(STOCK_FILE, list)
    for item in stock:
        if item["codigo"] == codigo:
            if item["quantidade"] < qtd:
                flash("Quantidade para retirada é maior que a disponível.")
                return redirect(url_for("inventory"))
            item["quantidade"] -= qtd
            save_data(STOCK_FILE, stock)
            log_action(f"Retirou {qtd} unid. do item '{item['nome']}' (Cód: {codigo})", session["username"])
            flash("Retirada efetuada com sucesso!")
            return redirect(url_for("inventory"))
    flash("Item não encontrado.")
    return redirect(url_for("inventory"))

@app.route("/transfer_inventory", methods=["POST"])
def transfer_inventory():
    """Transfere item do estoque principal para um subestoque (ação restrita)."""
    if "username" not in session or session["role"] == "nv1":
        flash("Ação não autorizada.")
        return redirect(url_for("inventory"))

    codigo = request.form.get("codigo")
    sub_id = request.form.get("subestoque_id")
    try:
        qtd = int(request.form.get("quantidade"))
    except ValueError:
        flash("Quantidade inválida.")
        return redirect(url_for("inventory"))

    stock = load_data(STOCK_FILE, list)
    item = next((i for i in stock if i["codigo"] == codigo), None)
    if not item:
        flash("Item não encontrado no estoque principal.")
        return redirect(url_for("inventory"))
    if item["quantidade"] < qtd:
        flash("Quantidade insuficiente para transferência.")
        return redirect(url_for("inventory"))

    item["quantidade"] -= qtd
    save_data(STOCK_FILE, stock)

    subinventories = load_data(SUBSTOCK_FILE, list)
    sub = next((s for s in subinventories if s["id"] == sub_id), None)
    if not sub:
        flash("Subestoque não encontrado.")
        return redirect(url_for("inventory"))
    sub.setdefault("itens", [])
    sub_item = next((i for i in sub["itens"] if i["codigo"] == codigo), None)
    if sub_item:
        sub_item["quantidade"] += qtd
    else:
        sub["itens"].append({
            "codigo": item["codigo"],
            "nome": item["nome"],
            "tipo": item["tipo"],
            "quantidade": qtd,
            "fabricante": item.get("fabricante", ""),
            "voltagem": item.get("voltagem", ""),
            "nivel_critico": item.get("nivel_critico")
        })
    save_data(SUBSTOCK_FILE, subinventories)
    log_action(f"Transferiu {qtd} de {item['nome']} para subestoque '{sub.get('nome','')}'", session["username"])
    flash("Transferência realizada com sucesso!")
    return redirect(url_for("inventory"))

@app.route("/delete_inventory/<codigo>")
def delete_inventory(codigo):
    """Exclui item do estoque principal; permitido apenas para nv3."""
    if "username" not in session or session["role"] != "nv3":
        flash("Ação não autorizada.")
        return redirect(url_for("inventory"))
    stock = load_data(STOCK_FILE, list)
    novo_stock = [i for i in stock if i["codigo"] != codigo]
    if len(novo_stock) == len(stock):
        flash("Item não encontrado.")
        return redirect(url_for("inventory"))
    save_data(STOCK_FILE, novo_stock)
    log_action(f"Excluiu item (Cód: {codigo})", session["username"])
    flash("Item excluído com sucesso!")
    return redirect(url_for("inventory"))

@app.route("/subinventories")
def subinventories():
    """Lista todos os subestoques (acesso mediante login)."""
    if "username" not in session:
        flash("Faça login.")
        return redirect(url_for("login"))
    subs = load_data(SUBSTOCK_FILE, list)
    return render_template("subinventories.html", subinventories=subs)

@app.route("/add_subinventory", methods=["POST"])
def add_subinventory():
    """Cria subestoque e, opcionalmente, associa usuário subusuário."""
    if "username" not in session:
        return redirect(url_for("login"))
    nome = request.form.get("nome", "").strip()
    user_sub = request.form.get("user_sub", "").strip()
    pass_sub = request.form.get("pass_sub", "").strip()

    subs = load_data(SUBSTOCK_FILE, list)
    if any(s["nome"].lower() == nome.lower() for s in subs):
        flash("Subestoque já existe.")
        return redirect(url_for("subinventories"))
    max_id = max((int(s["id"]) for s in subs), default=0)
    novo_id = str(max_id + 1).zfill(4)
    subs.append({"id": novo_id, "nome": nome, "itens": []})
    save_data(SUBSTOCK_FILE, subs)
    log_action(f"Criou subestoque '{nome}' (ID: {novo_id})", session["username"])

    # Cria usuário para subestoque se informado
    if user_sub and pass_sub:
        users = load_data(USERS_FILE, list)
        if any(u["username"].lower() == user_sub.lower() for u in users):
            flash("Login para subusuário já existe.")
            return redirect(url_for("subinventories"))
        novo_user = {
            "username": user_sub,
            "password": pass_sub,
            "role": "nv1",
            "sub_id": novo_id,
            "sub_nome": nome
        }
        users.append(novo_user)
        save_data(USERS_FILE, users)
        log_action(f"Criou usuário nv1 '{user_sub}' para subestoque '{nome}'", session["username"])
        flash("Subestoque e usuário associados criados com sucesso!")
    else:
        flash("Subestoque adicionado com sucesso!")
    return redirect(url_for("subinventories"))

@app.route("/manage_users")
def manage_users():
    if "username" not in session or session["role"] != "nv3":
        flash("Acesso restrito somente a Cargos Superiores.")
        return redirect(url_for("dashboard"))
    all_users = load_data(USERS_FILE, list)
    subinventories = load_data(SUBSTOCK_FILE, list)
    # sub_to_user pode ser usado para relacionamentos, se necessário
    sub_to_user = {u["sub_id"]: u for u in all_users if u.get("role") == "nv1" and "sub_id" in u}
    return render_template("admin.html",
                           all_users=all_users,
                           subinventories=subinventories,
                           sub_to_user=sub_to_user)

@app.route("/create_user", methods=["GET", "POST"])
def create_user():
    if "username" not in session or session["role"] != "nv3":
        flash("Acesso restrito somente a Cargos Superiores.")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()
        users = load_data(USERS_FILE, list)
        if any(u["username"].lower() == username.lower() for u in users):
            flash("Usuário já existe.")
            return redirect(url_for("manage_users"))
        
        new_user = {
            "username": username,
            "password": password,
            "role": role
        }
        
        if request.form.get("create_stock"):
            subinventories = load_data(SUBSTOCK_FILE, list)
            max_id = max((int(s["id"]) for s in subinventories), default=0)
            new_sub_id = str(max_id + 1).zfill(4)
            sub_nome = request.form.get("sub_nome", f"{username} Estoque").strip()
            if not sub_nome:
                sub_nome = f"{username} Estoque"
            new_sub = {
                "id": new_sub_id,
                "nome": sub_nome,
                "itens": []
            }
            subinventories.append(new_sub)
            save_data(SUBSTOCK_FILE, subinventories)
            new_user["sub_id"] = new_sub_id
            new_user["sub_nome"] = sub_nome
        
        users.append(new_user)
        save_data(USERS_FILE, users)
        # Aqui é onde o log é gerado
        log_action(f"Criou usuário '{username}'", session["username"])
        flash("Usuário criado com sucesso!")
        return redirect(url_for("manage_users"))
    return render_template("create_user.html")


@app.route("/edit_user/<username>", methods=["GET", "POST"])
def edit_user(username):
    if "username" not in session or session["role"] != "nv3":
        flash("Acesso restrito somente a Cargos Superiores.")
        return redirect(url_for("dashboard"))
    users = load_data(USERS_FILE, list)
    user_to_edit = next((u for u in users if u["username"].lower() == username.lower()), None)
    if not user_to_edit:
        flash("Usuário não encontrado.")
        return redirect(url_for("manage_users"))
    if request.method == "POST":
        novo_username = request.form.get("username", "").strip()
        novo_role = request.form.get("role", "").strip()
        novo_pass = request.form.get("password", "").strip()
        novo_sub_id = request.form.get("sub_id", "").strip()
        novo_sub_nome = request.form.get("sub_nome", "").strip()
        if not novo_username or not novo_role:
            flash("Os campos de nome de usuário e cargo não podem estar vazios.")
            return redirect(url_for("edit_user", username=username))
        if user_to_edit["username"].lower() == session["username"].lower() and novo_role != user_to_edit["role"]:
            flash("Você não pode alterar seu próprio cargo.")
            return redirect(url_for("edit_user", username=username))
        user_to_edit["username"] = novo_username
        user_to_edit["role"] = novo_role
        if novo_pass:
            user_to_edit["password"] = novo_pass
        if novo_role.lower() in ("nv1", "nv2"):
            user_to_edit["sub_id"] = novo_sub_id
            user_to_edit["sub_nome"] = novo_sub_nome
        save_data(USERS_FILE, users)
        log_action(f"Editou usuário '{username}'; novo cargo: {novo_role}", session["username"])
        flash("Usuário atualizado com sucesso!")
        return redirect(url_for("manage_users"))
    return render_template("edit_user.html", user=user_to_edit)

@app.route("/delete_user/<username>")
def delete_user(username):
    """Exclui usuário (não permitido autodeleção); acesso restrito somente a Cargos Superiores."""
    if "username" not in session or session["role"] != "nv3":
        flash("Acesso restrito somente a Cargos Superiores.")
        return redirect(url_for("dashboard"))
    if username.lower() == session["username"].lower():
        flash("Você não pode excluir seu próprio usuário.")
        return redirect(url_for("manage_users"))
    users = load_data(USERS_FILE, list)
    novo_users = [u for u in users if u["username"].lower() != username.lower()]
    if len(novo_users) == len(users):
        flash("Usuário não encontrado.")
    else:
        save_data(USERS_FILE, novo_users)
        log_action(f"Excluiu usuário '{username}'", session["username"])
        flash("Usuário excluído com sucesso!")
    return redirect(url_for("manage_users"))

@app.route("/subinventory/<sub_id>")
def subinventory_detail(sub_id):
    """Exibe detalhes de um subestoque específico."""
    if "username" not in session:
        flash("Faça login.")
        return redirect(url_for("login"))
    subs = load_data(SUBSTOCK_FILE, list)
    sub = next((s for s in subs if s["id"] == sub_id), None)
    if not sub:
        flash("Subestoque não encontrado.")
        return redirect(url_for("subinventories"))
    return render_template("subinventory_detail.html", subinventory=sub)

@app.route("/delete_subinventory/<sub_id>")
def delete_subinventory(sub_id):
    """Exclui subestoque; acesso restrito somente a Cargos Superiores."""
    if "username" not in session or session["role"] != "nv3":
        flash("Ação não autorizada.")
        return redirect(url_for("subinventories"))
    subs = load_data(SUBSTOCK_FILE, list)
    novo_subs = [s for s in subs if s["id"] != sub_id]
    if len(novo_subs) == len(subs):
        flash("Subestoque não encontrado.")
        return redirect(url_for("subinventories"))
    save_data(SUBSTOCK_FILE, novo_subs)
    log_action(f"Excluiu subestoque (ID: {sub_id})", session["username"])
    flash("Subestoque excluído com sucesso!")
    return redirect(url_for("subinventories"))


# ────────────────────────────── SESSÃO: CHAMADOS (TICKETS) ──────────────────────────────
def list_chamados():
    """Retorna a lista de chamados."""
    return load_data(CHAMADOS_FILE, list)

def save_chamados(data):
    """Salva a lista de chamados."""
    save_data(CHAMADOS_FILE, data)

def next_chamado_id():
    """Gera o próximo ID para chamado."""
    ch = list_chamados()
    return max((c["id"] for c in ch), default=0) + 1

@app.route("/chamados")
def chamados():
    """Exibe chamados divididos por status."""
    if "username" not in session:
        flash("Faça login primeiro.")
        return redirect(url_for("login"))
    ch_all = list_chamados()[::-1]  # Mais recentes no topo
    pendentes = [c for c in ch_all if c["status"] in ("Aberto", "Aguardando Peça")]
    nao_resolvidos = [c for c in ch_all if c["status"] == "Outro"]
    resolvidos = [c for c in ch_all if c["status"] == "Resolvido"]
    return render_template(
        "chamados.html",
        pendentes=pendentes,
        nao_resolvidos=nao_resolvidos,
        resolvidos=resolvidos,
        current_date=datetime.date.today().isoformat(),
        current_time=datetime.datetime.now().strftime("%H:%M")
    )

@app.route("/add_chamado", methods=["POST"])
def add_chamado():
    """Cria novo chamado; ação não permitida para subusuário."""
    if "username" not in session or session["role"] == "nv1":
        flash("Ação não autorizada.")
        return redirect(url_for("chamados"))
    novo = {
        "id": next_chamado_id(),
        "cliente": request.form.get("cliente", "").strip(),
        "maquina": request.form.get("maquina", "").strip(),
        "data": request.form.get("data"),
        "hora": request.form.get("hora"),
        "status": request.form.get("status"),
        "data_resolvido": ""
    }
    ch = list_chamados()
    ch.append(novo)
    save_chamados(ch)
    log_action(f"Novo chamado #{novo['id']} para {novo['cliente']}", session["username"])
    flash("Chamado registrado.")
    return redirect(url_for("chamados"))

@app.route("/update_chamado_status/<int:cid>", methods=["POST"])
def update_chamado_status(cid):
    """Atualiza status do chamado e ajusta data de resolução, se aplicável."""
    if "username" not in session:
        flash("Faça login primeiro.")
        return redirect(url_for("login"))
    novo_status = request.form.get("novo_status", "").strip()
    if not novo_status:
        flash("Status inválido.")
        return redirect(url_for("chamados"))
    ch = list_chamados()
    found = False
    for c in ch:
        if c["id"] == cid:
            c["status"] = novo_status
            if novo_status.lower() == "resolvido":
                c["data_resolvido"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            else:
                c["data_resolvido"] = ""
            found = True
            break
    if not found:
        flash("Chamado não encontrado.")
        return redirect(url_for("chamados"))
    save_chamados(ch)
    log_action(f"Chamado #{cid} → {novo_status}", session["username"])
    flash("Status atualizado.")
    return redirect(url_for("chamados"))

@app.route("/create_cliente", methods=["POST"])
def create_cliente():
    """Cria novo cliente para uso em chamados; ação não permitida para subusuário."""
    if "username" not in session or session["role"] == "nv1":
        flash("Ação não autorizada.")
        return redirect(url_for("chamados"))
    clientes = load_data(CLIENTES_FILE, list)
    novo_id = str(len(clientes) + 1).zfill(4)
    novo_cliente = {
        "id": novo_id,
        "nome": request.form.get("nome", "").strip(),
        "regiao": request.form.get("regiao", "").strip(),
        "referencia": request.form.get("referencia", "").strip()
    }
    clientes.append(novo_cliente)
    save_data(CLIENTES_FILE, clientes)
    log_action(f"Criou cliente '{novo_cliente['nome']}'", session["username"])
    flash("Cliente criado com sucesso.")
    return redirect(url_for("chamados"))

# ────────────────────────────── SESSÃO: UTILIDADES ──────────────────────────────

# Função para alterar a senha do usuário.
# - Verifica se o usuário está logado
# - Checa se a senha atual está correta
# - Valida que a nova senha não está vazia
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")

        if not new:
            flash("Nova senha não pode ser vazia.")
            return redirect(url_for("change_password"))

        users = load_users()
        user_found = False
        for u in users:
            if u["username"] == session["username"]:
                user_found = True
                if u["password"] != current:
                    flash("Senha atual incorreta.")
                    return redirect(url_for("change_password"))
                u["password"] = new
                save_users(users)
                log_action("Alterou senha", session["username"])
                flash("Senha alterada com sucesso!")
                return redirect(url_for("inventory"))
        # Caso o usuário não seja encontrado (improvável)
        if not user_found:
            flash("Usuário não encontrado.")
            return redirect(url_for("login"))

    return render_template("change_password.html")


# Função que exporta os itens selecionados do estoque para um arquivo PDF.
# - Valida se há itens selecionados e disponíveis para exportação
# - Gera o PDF em memória (BytesIO) evitando I/O desnecessário em disco
from fpdf import FPDF
from io import BytesIO
from flask import send_file, flash, redirect, url_for

@app.route("/export_pdf", methods=["POST"])
def export_pdf():
    # Obtém o contexto de exportação: "inventory" ou "chamados"
    export_context = request.form.get("export_context", "inventory")
    
    # Dependendo do contexto, os nomes dos checkboxes podem ser diferentes:
    if export_context == "chamados":
        codigos = request.form.getlist("chamado_ids")
    else:
        codigos = request.form.getlist("codigos")
    
    if not codigos:
        flash("Nenhum item selecionado para exportação.")
        if export_context == "chamados":
            return redirect(url_for("chamados"))
        else:
            return redirect(url_for("inventory"))
    
    # Carrega os dados e filtra os itens selecionados
    if export_context == "chamados":
        dados = load_data(CHAMADOS_FILE, list)
        # Usamos str(i["id"]) para compatibilidade, caso os valores sejam números
        itens = [i for i in dados if str(i["id"]) in codigos]
    else:
        dados = load_data(STOCK_FILE, list)
        itens = [i for i in dados if i["codigo"] in codigos and int(i["quantidade"]) > 0]
    
    if not itens:
        flash("Nenhum item disponível para exportação.")
        if export_context == "chamados":
            return redirect(url_for("chamados"))
        else:
            return redirect(url_for("inventory"))
    
    # Cria o PDF usando FPDF e a fonte DejaVuSans (certifique-se de que o arquivo está em "fonts/DejaVuSans.ttf")
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('DejaVu', '', 'fonts/DejaVuSans.ttf', uni=True)
    pdf.set_font("DejaVu", "", 12)

    # OBSERVAÇÃO: Removemos os emojis para evitar erros de largura na fonte
    if export_context == "chamados":
        pdf.cell(0, 10, txt="Relatório de Chamados - i9 Café", ln=True, align="C")
        pdf.ln(5)
        # Para cada chamado, imprime os dados, incluindo prioridade e data resolvido, se houver.
        for it in itens:
            pdf.cell(0, 8, txt=f"ID: {it['id']}", ln=True)
            pdf.cell(0, 8, txt=f"Cliente: {it['cliente']}", ln=True)
            pdf.cell(0, 8, txt=f"Máquina: {it['maquina']}", ln=True)
            pdf.cell(0, 8, txt=f"Data: {it['data']}", ln=True)
            pdf.cell(0, 8, txt=f"Hora: {it['hora']}", ln=True)
            pdf.cell(0, 8, txt=f"Status: {it['status']}", ln=True)
            if it.get("prioridade"):
                pdf.cell(0, 8, txt=f"Prioridade: {it['prioridade']}", ln=True)
            if it.get("data_resolvido"):
                pdf.cell(0, 8, txt=f"Data Resolvido: {it['data_resolvido']}", ln=True)
            pdf.ln(3)
        filename = "chamados_exportado.pdf"
    else:
        pdf.cell(0, 10, txt="Relatório de Estoque - i9 Café", ln=True, align="C")
        pdf.ln(5)
        for it in itens:
            pdf.cell(0, 8, txt=f"Código: {it['codigo']}", ln=True)
            pdf.cell(0, 8, txt=f"Nome: {it['nome']}", ln=True)
            pdf.cell(0, 8, txt=f"Tipo: {it.get('tipo', '')}", ln=True)
            pdf.cell(0, 8, txt=f"Quantidade: {it['quantidade']}", ln=True)
            if it.get('fabricante'):
                pdf.cell(0, 8, txt=f"Fabricante: {it.get('fabricante', '')}", ln=True)
            if it.get('voltagem'):
                pdf.cell(0, 8, txt=f"Voltagem/Amperagem: {it.get('voltagem', '')}", ln=True)
            if it.get('nivel_critico') is not None:
                pdf.cell(0, 8, txt=f"Nível Crítico: {it.get('nivel_critico', '')}", ln=True)
            pdf.ln(3)
        filename = "estoque_exportado.pdf"
    
    try:
        pdf_output = pdf.output(dest="S").encode("latin1")
    except Exception as e:
        flash("Erro ao gerar PDF: " + str(e))
        if export_context == "chamados":
            return redirect(url_for("chamados"))
        else:
            return redirect(url_for("inventory"))
    
    pdf_buffer = BytesIO(pdf_output)
    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )


# Função para exibir os logs do sistema.
# - Apenas usuários do tipo nv3 podem acessar
# - Permite filtro de logs via parâmetro GET (?filtro=texto)
@app.route("/logs")
def logs():
    if "username" not in session or session["role"] != "nv3":
        return redirect(url_for("dashboard"))

    dados = load_data(LOGS_FILE, list)
    filtro = request.args.get("filtro", "").lower()
    if filtro:
        dados = [l for l in dados if filtro in l["action"].lower()]

    return render_template("logs.html", logs=dados, filtro=filtro)


# Função para encerrar a sessão do usuário.
# - Registra a ação de logout e limpa os dados da sessão
@app.route("/logout")
def logout():
    log_action("Logout", session.get("username", "desconhecido"))
    session.clear()
    flash("Você saiu do sistema.")
    return redirect(url_for("login"))


# ────────────────────────────── MAIN ──────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
