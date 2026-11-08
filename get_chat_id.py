#!/usr/bin/env python3
"""Script de ayuda para obtener tu Telegram Chat ID y User ID.
Uso:
    python get_chat_id.py
    python get_chat_id.py TU_TELEGRAM_BOT_TOKEN
"""

import os
from pathlib import Path
import sys
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def find_token() -> str:
    """Busca el token en argumentos, .env o .env.save."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()

    env_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if env_token and "PEGA_AQUI" not in env_token:
        return env_token.strip()

    # Revisar .env.save si existe
    save_file = BASE_DIR / ".env.save"
    if save_file.exists():
        for line in save_file.read_text().splitlines():
            if line.startswith("TELEGRAM_TOKEN=") or line.startswith("TELEGRAM_BOT_TOKEN="):
                val = line.split("=", 1)[1].strip()
                if val and "PEGA_AQUI" not in val:
                    return val

    # Solicitar por teclado si no se encuentra
    print("=" * 60)
    print("      ASISTENTE DE CONFIGURACIÓN DE TELEGRAM")
    print("=" * 60)
    try:
        user_input = input("Introduce el Token de tu bot (obtenido de @BotFather): ").strip()
        return user_input
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        sys.exit(1)


def main():
    token = find_token()
    if not token or len(token) < 15 or ":" not in token:
        print("\n❌ Error: El token proporcionado no parece válido.")
        print("Asegúrate de obtener el token de @BotFather con el formato: 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    print(f"\nConsultando actualizaciones en Telegram...")

    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if not data.get("ok"):
            print(f"❌ Error en Telegram API: {data.get('description', 'Token inválido')}")
            sys.exit(1)

        results = data.get("result", [])
        if not results:
            print("\n⚠️ No se encontraron mensajes recientes.")
            print("=" * 60)
            print("PASOS A SEGUIR:")
            print("1. Abre Telegram en tu teléfono o computadora.")
            print("2. Busca tu bot por su @username.")
            print("3. Presiona el botón 'Iniciar' o envíale un mensaje: Hola")
            print("4. Vuelve a ejecutar este comando:")
            print(f"   python get_chat_id.py {token}")
            print("=" * 60)
            return

        # Extraer el chat_id y user_id del mensaje más reciente
        last_msg = results[-1].get("message") or results[-1].get("channel_post") or {}
        chat = last_msg.get("chat", {})
        user = last_msg.get("from", {})

        chat_id = chat.get("id")
        user_id = user.get("id")
        username = user.get("username") or chat.get("username") or "N/A"
        first_name = user.get("first_name") or chat.get("first_name") or "Usuario"

        print("\n✅ ¡DATOS DE TELEGRAM ENCONTRADOS CON ÉXITO!")
        print("=" * 60)
        print(f"• Nombre:       {first_name}")
        print(f"• Usuario:      @{username}")
        print(f"• Chat ID:      {chat_id}")
        print(f"• User ID:      {user_id}")
        print("=" * 60)
        print("\nAgrega estas líneas a tu archivo .env:")
        print(f"TELEGRAM_BOT_TOKEN={token}")
        print(f"TELEGRAM_CHAT_ID={chat_id}")
        print(f"TELEGRAM_AUTHORIZED_USERS={user_id}")
        print("=" * 60)

        # Preguntar si desea actualizar .env automáticamente
        env_path = BASE_DIR / ".env"
        try:
            choice = input("\n¿Deseas guardar automáticamente estos valores en .env? (s/n): ").strip().lower()
            if choice in ("s", "si", "y", "yes"):
                lines = []
                if env_path.exists():
                    lines = env_path.read_text().splitlines()

                updated = False
                new_lines = []
                keys_set = set()

                for line in lines:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        new_lines.append(f"TELEGRAM_BOT_TOKEN={token}")
                        keys_set.add("TELEGRAM_BOT_TOKEN")
                    elif line.startswith("TELEGRAM_CHAT_ID="):
                        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
                        keys_set.add("TELEGRAM_CHAT_ID")
                    elif line.startswith("TELEGRAM_AUTHORIZED_USERS="):
                        new_lines.append(f"TELEGRAM_AUTHORIZED_USERS={user_id}")
                        keys_set.add("TELEGRAM_AUTHORIZED_USERS")
                    else:
                        new_lines.append(line)

                if "TELEGRAM_BOT_TOKEN" not in keys_set:
                    new_lines.append(f"TELEGRAM_BOT_TOKEN={token}")
                if "TELEGRAM_CHAT_ID" not in keys_set:
                    new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
                if "TELEGRAM_AUTHORIZED_USERS" not in keys_set:
                    new_lines.append(f"TELEGRAM_AUTHORIZED_USERS={user_id}")

                env_path.write_text("\n".join(new_lines) + "\n")
                print("✅ Archivo .env actualizado exitosamente.")
        except Exception as e:
            print(f"No se pudo guardar automáticamente en .env: {e}")

    except Exception as e:
        print(f"❌ Error de conexión: {e}")


if __name__ == "__main__":
    main()
