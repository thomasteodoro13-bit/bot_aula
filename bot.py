import logging
import requests
import base64
import json
import os
from datetime import datetime, timedelta, time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ==============================
# CONFIG
# ==============================
TOKEN = os.getenv("TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

REPO = "SEU_USUARIO/SEU_REPO"
ARQUIVO = "registros.json"

CANAL_ID = -1003970171653

NOME = 1

logging.basicConfig(level=logging.INFO)

# ==============================
# GITHUB API
# ==============================
def get_file():
    url = f"https://api.github.com/repos/{REPO}/contents/{ARQUIVO}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)
    data = r.json()

    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]

def update_file(content, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{ARQUIVO}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    new_content = base64.b64encode(
        json.dumps(content, indent=4).encode("utf-8")
    ).decode("utf-8")

    data = {
        "message": "Atualizando registros",
        "content": new_content,
        "sha": sha
    }

    requests.put(url, headers=headers, json=data)

# ==============================
# UTIL
# ==============================
def semana_atual():
    ano, semana, _ = datetime.now().isocalendar()
    return f"{ano}-S{semana}"

def ja_usou_na_semana(user_id):
    dados, _ = get_file()
    semana = semana_atual()

    for user in dados:
        if user["user_id"] == str(user_id) and user["semana"] == semana:
            return True

    return False

def salvar_registro(nome, username, user_id):
    dados, sha = get_file()

    dados.append({
        "nome": nome,
        "username": username,
        "user_id": str(user_id),
        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "semana": semana_atual()
    })

    update_file(dados, sha)

# ==============================
# /aula
# ==============================
async def aula(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if ja_usou_na_semana(user.id):
        await update.message.reply_text(
            "Você já acessou a reposição desta semana."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Informe seu nome completo para liberar a reposição:"
    )
    return NOME

# ==============================
# RECEBER NOME
# ==============================
async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nome = update.message.text
        user = update.effective_user

        salvar_registro(
            nome,
            user.username if user.username else "sem_username",
            user.id
        )

        expire_date = datetime.now() + timedelta(hours=48)

        link = await context.bot.create_chat_invite_link(
            chat_id=CANAL_ID,
            member_limit=1,
            expire_date=expire_date
        )

        context.job_queue.run_once(
            remover_usuario,
            when=timedelta(hours=48),
            data={"user_id": user.id}
        )

        await update.message.reply_text(
            f"Acesso liberado por 48h.\n\n{link.invite_link}"
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        await update.message.reply_text("Erro. Tente novamente.")

    return ConversationHandler.END

# ==============================
# REMOVER USUÁRIO
# ==============================
async def remover_usuario(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]

    try:
        await context.bot.ban_chat_member(CANAL_ID, user_id)
        await context.bot.unban_chat_member(CANAL_ID, user_id)
    except:
        pass

# ==============================
# LIMPEZA SEMANAL
# ==============================
async def limpar_usuarios_semana(context: ContextTypes.DEFAULT_TYPE):
    dados, _ = get_file()

    admins = await context.bot.get_chat_administrators(CANAL_ID)
    admin_ids = [admin.user.id for admin in admins]

    for user in dados:
        user_id = int(user["user_id"])

        if user_id in admin_ids:
            continue

        try:
            await context.bot.ban_chat_member(CANAL_ID, user_id)
            await context.bot.unban_chat_member(CANAL_ID, user_id)
        except:
            pass

# ==============================
# CANCELAR
# ==============================
async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

# ==============================
# MAIN
# ==============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("aula", aula)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)]
        },
        fallbacks=[
            CommandHandler("cancelar", cancelar),
            MessageHandler(filters.ALL, cancelar)
        ]
    )

    app.add_handler(conv_handler)

    app.job_queue.run_daily(
        limpar_usuarios_semana,
        time=time(hour=23, minute=59),
        days=(6,)
    )

    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()