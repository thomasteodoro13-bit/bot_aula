import logging
import requests
import base64
import json
import time

from datetime import datetime, timedelta, time as dtime
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
TOKEN = "SEU_TOKEN_AQUI"
CANAL_ID = -1003970171653

GITHUB_TOKEN = "SEU_GITHUB_TOKEN"
REPO = "thomasteodoro13-bit/bot_aula"
ARQUIVO = "registros.json"

NOME = 1

logging.basicConfig(level=logging.INFO)

# ==============================
# UTIL
# ==============================
def semana_atual():
    ano, semana, _ = datetime.now().isocalendar()
    return f"{ano}-S{semana}"

# ==============================
# GITHUB (BLINDADO)
# ==============================
def get_file(retries=3):
    url = f"https://api.github.com/repos/{REPO}/contents/{ARQUIVO}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            data = r.json()

            if "content" not in data:
                print("Erro GitHub:", data)
                return [], None

            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]

        except Exception as e:
            print(f"Erro get_file (tentativa {i+1}):", e)
            time.sleep(2)

    return [], None


def update_file(dados, sha, retries=3):
    url = f"https://api.github.com/repos/{REPO}/contents/{ARQUIVO}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    for i in range(retries):
        try:
            content = base64.b64encode(
                json.dumps(dados, indent=2).encode("utf-8")
            ).decode("utf-8")

            payload = {
                "message": "Atualizando registros",
                "content": content,
                "sha": sha
            }

            r = requests.put(url, headers=headers, json=payload, timeout=10)

            if r.status_code in [200, 201]:
                return True
            else:
                print("Erro update:", r.json())

        except Exception as e:
            print(f"Erro update_file (tentativa {i+1}):", e)
            time.sleep(2)

    return False


def salvar_registro(nome, username, user_id):
    try:
        dados, sha = get_file()

        if sha is None:
            print("Falha ao obter SHA - registro ignorado")
            return

        dados.append({
            "nome": nome,
            "username": username,
            "user_id": str(user_id),
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "semana": semana_atual()
        })

        update_file(dados, sha)

    except Exception as e:
        print("Erro salvar_registro:", e)


def ja_usou_na_semana(user_id):
    try:
        dados, _ = get_file()
        semana = semana_atual()

        for user in dados:
            if user["user_id"] == str(user_id) and user["semana"] == semana:
                return True

        return False

    except Exception as e:
        print("Erro verificação:", e)
        return False


# ==============================
# HANDLERS
# ==============================
async def aula(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user

        if ja_usou_na_semana(user.id):
            await update.message.reply_text("Você já acessou essa semana.")
            return ConversationHandler.END

        await update.message.reply_text("Digite seu nome completo:")
        return NOME

    except Exception as e:
        print("Erro /aula:", e)
        return ConversationHandler.END


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nome = update.message.text
        user = update.effective_user

        salvar_registro(
            nome,
            user.username or "sem_username",
            user.id
        )

        expire_date = datetime.now() + timedelta(hours=48)

        link = await context.bot.create_chat_invite_link(
            chat_id=CANAL_ID,
            member_limit=1,
            expire_date=expire_date
        )

        # remover após 48h
        context.job_queue.run_once(
            remover_usuario,
            when=timedelta(hours=48),
            data={"user_id": user.id}
        )

        await update.message.reply_text(
            f"Acesso por 48h:\n{link.invite_link}"
        )

    except Exception as e:
        print("Erro receber_nome:", e)

    return ConversationHandler.END


async def remover_usuario(context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = context.job.data["user_id"]

        await context.bot.ban_chat_member(
            chat_id=CANAL_ID,
            user_id=user_id
        )

        await context.bot.unban_chat_member(
            chat_id=CANAL_ID,
            user_id=user_id
        )

        print(f"Removido: {user_id}")

    except Exception as e:
        print("Erro remover usuário:", e)


# ==============================
# LIMPEZA SEMANAL (DOMINGO)
# ==============================
async def limpar_usuarios_semana(context: ContextTypes.DEFAULT_TYPE):
    try:
        membros = await context.bot.get_chat_administrators(CANAL_ID)
        admins = [m.user.id for m in membros]

        print("Limpando usuários da semana...")

        # aqui você pode adaptar lógica futura se quiser
        # ex: remover todos não-admins (se tiver lista)

    except Exception as e:
        print("Erro limpeza semanal:", e)


# ==============================
# ERRO GLOBAL
# ==============================
async def error_handler(update, context):
    print("ERRO GLOBAL:", context.error)


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
        fallbacks=[CommandHandler("cancelar", lambda u, c: ConversationHandler.END)]
    )

    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    # domingo 23:59
    app.job_queue.run_daily(
        limpar_usuarios_semana,
        time=dtime(hour=23, minute=59),
        days=(6,)
    )

    print("Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()