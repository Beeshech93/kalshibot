# ⚡ BTC SCALPING AI — Sistema Autónomo de Análisis y Señales para Kalshi

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-brightgreen.svg)]()
[![Status: Modo Solo Señales](https://img.shields.io/badge/Mode-SOLO__SE%C3%91ALES-orange.svg)]()

**BTC SCALPING AI** es una plataforma institucional modular y autónoma diseñada para analizar continuamente el precio de Bitcoin (BTC/USDT) y los contratos de predicción binaria en **Kalshi** (serie principal `KXBTC15M` con fallbacks dinámicos), generando señales de alta probabilidad (`YES`, `NO`, `WAIT`), métricas de rendimiento histórico, notificaciones automáticas por **Telegram**, un **Dashboard Financiero Web** en tiempo real y scripts nativos para **TradingView (Pine Script v6)**.

> ⚠️ **IMPORTANTE:** El sistema opera **exclusivamente en modo de análisis y generación de señales**. Por diseño de seguridad, **no ejecuta transacciones financieras reales**.

---

## 🏛️ Arquitectura del Proyecto

```
btc-scalping-ai/
├── app/
│   ├── main.py                 # Orquestador del sistema y manejo de señales de apagado
│   ├── config.py               # Gestión tipada de variables de entorno y seguridad
│   ├── market_data.py          # Agregador de precio spot BTC y velas cerradas multi-temporalidad
│   ├── kalshi_client.py        # Conector oficial con Kalshi API v2 (descubrimiento y parsing)
│   ├── technical_analysis.py   # Motor matemático: EMA (9, 21, 50), RSI, MACD y Volumen
│   ├── signal_engine.py        # Generador de señales YES/NO/WAIT con puntuación heurística 0-100
│   ├── telegram_bot.py         # Bot interactivo con comandos autorizados y alertas cada 15m
│   ├── scheduler.py            # Planificador concurrente de ciclos de 15 minutos
│   ├── database.py             # Capa de persistencia SQLite (inmutable y transaccional)
│   └── performance.py          # Cálculo objetivo de Win Rate (excluyendo pendientes)
│
├── dashboard/
│   ├── app.py                  # Servidor web Flask y API REST interna
│   ├── templates/
│   │   └── index.html          # Interfaz financiera responsiva (Tema Oscuro)
│   └── static/
│       ├── css/style.css       # Estilos CSS dark-mode de grado institucional
│       └── js/dashboard.js     # Gráficos Chart.js en tiempo real y sondeo continuo
│
├── tradingview/
│   └── btc_scalping.pine       # Indicador Pine Script v6 completo con alertas webhook
│
├── tests/
│   ├── test_indicators.py      # Pruebas unitarias de algoritmos matemáticos
│   ├── test_signals.py         # Pruebas de reglas de decisión y prevención de duplicados
│   ├── test_kalshi.py          # Pruebas de cliente Kalshi y tolerancia a fallos
│   └── test_dashboard.py       # Pruebas de endpoints REST del dashboard web
│
├── data/                       # Base de datos SQLite (data/btc_scalping.db)
├── logs/                       # Registros rotativos del sistema
├── com.btcscalping.ai.plist    # Archivo de servicio daemon para macOS launchd
├── .env.example                # Plantilla de variables de entorno
├── .gitignore                  # Protección de secretos, venv y logs
├── requirements.txt            # Dependencias del entorno
├── README.md                   # Documentación oficial
└── run.py                      # Ejecutor CLI principal (Bot + Dashboard)
```

---

## 🔬 Análisis Técnico y Motor de Señales

### 1. Indicadores Implementados
- **Medias Móviles Exponenciales (EMA):**
  - `EMA 9`: Impulso y gatillo a muy corto plazo.
  - `EMA 21`: Línea de tendencia media y soporte dinámico.
  - `EMA 50`: Tendencia estructural macro.
- **Relative Strength Index (RSI 14):**
  - Implementación con suavizado de Wilder.
  - Filtro de momentum: Zona alcista (52 - 70), zona bajista (30 - 48).
  - Penalizaciones por agotamiento extremo (> 75 o < 25).
- **MACD (12, 26, 9):**
  - Cruces de línea de señal y polaridad del histograma.
- **Filtro de Volumen:**
  - Volumen medio de 20 periodos (`SMA 20`).
  - `Confirmación`: Volumen de la vela cerrada superior a la media.
  - `Anomalía`: Detección de picos volumétricos institucionales (> 2x la media).

### 2. Multi-Temporalidad y Velas Cerradas
El bot analiza simultáneamente temporalidades de **1m, 5m y 15m**.
Para evitar repintado o sesgos producidos por datos provisionales, **únicamente se evalúan velas completamente cerradas**.

### 3. Sistema de Señales
- **`YES`:** Estructura alcista alineada (EMA 9 > 21 > 50 con precio por encima), MACD positivo, RSI en rango saludable, confirmación de volumen y tiempo de contrato viable.
- **`NO`:** Estructura bajista alineada (EMA 9 < 21 < 50 con precio por debajo), MACD negativo, presión vendedora en RSI, confirmación de volumen.
- **`WAIT`:** Indecisión, conflicto entre temporalidades, volumen deficiente, tiempo de contrato crítico (< 90 segundos) o puntuación inferior al umbral mínimo (60%).

> **Nota sobre la Confianza del Modelo (0 a 100):** La puntuación es un score ponderado de confluencia técnica, presentado honestamente como puntuación heurística interna y no como probabilidad matemática real hasta completar la fase de calibración estadística.

---

## 🏛️ Integración con Kalshi

El conector `KalshiClient` se comunica con la API oficial v2 (`https://api.elections.kalshi.com/trade-api/v2`):
- **Serie Objetivo:** `KXBTC15M` (Mercados de Bitcoin a 15 minutos).
- **Descubrimiento Dinámico:** Si la serie objetivo no cuenta con mercados activos en un momento dado, el bot consulta ordenadamente las series de fallback configuradas (`KXBTCH`, `KXBTCD`, `KXBTC`).
- **Campos Inspeccionados:** Ticker, Título, Estado (`active`), Strike objetivo, Precios Ask/Bid de `YES` y `NO` (convertidos a centavos 0-100), Fecha y hora de liquidación, Tiempo restante y Reglas oficiales de liquidación (índice BRTI de CF Benchmarks).
- **Sin Credenciales Obligatorias:** Para la fase de análisis y señales se utiliza la API pública de mercados sin requerir llaves privadas.

---

## 🤖 Bot de Telegram

Compatible con la Telegram Bot API (`https://core.telegram.org/bots/api`).

### Comandos Interactivos
- `/start` — Inicia la interacción con el bot.
- `/status` — Informa el estado general del sistema y los parámetros operativos.
- `/btc` — Retorna el precio spot actual en tiempo real de Bitcoin.
- `/signal` — Muestra la última señal emitida con su justificación detallada.
- `/market` — Detalla el contrato activo en Kalshi, strike y precios YES/NO.
- `/history` — Historial de las últimas 5 señales generadas.
- `/performance` — Resumen estadístico (Wins, Losses, Win Rate, Pendientes).
- `/help` — Muestra el catálogo de comandos.

### Formato Exacto de Alerta (Cada 15 Minutos)
```text
BTC SCALPING AI

Mercado: BTC / USDT
Plataforma: KALSHI
Contrato: KXBTC15M-26NOV080215-15

Precio BTC: $75,846.00
Tendencia: BEARISH
RSI: 44.2
EMA 9: $75,820.00
EMA 21: $75,860.00
EMA 50: $75,900.00
MACD: -12.40
Volumen: Confirmado

SEÑAL: NO

Precio YES: 25¢
Precio NO: 76¢
Tiempo restante: 11m 40s

Confianza del modelo: 75.0% (Puntuación heurística de modelo)
Justificación técnica: 15m: Estructura bajista (EMA 9 < 21 < 50) | 15m: MACD negativo | 5m: Confirma bajada | Volumen institucional confirmado.

Modo: SOLO SEÑALES.
```

---

## 💻 Dashboard Web Financiero

Interfaz responsive desarrollada en Flask, CSS puro con temática oscura y gráficos en tiempo real con Chart.js:
- **Ticker Spot en Vivo:** Agregación continua de precios spot.
- **Gráfico Técnico:** Velas de 15 minutos y trazado en tiempo real de EMA 9, 21 y 50.
- **Contrato Kalshi Activo:** Tarjeta con cotizaciones bid/ask de YES/NO, strike y cuenta regresiva.
- **Métricas de Desempeño:** Win Rate %, Total de Aciertos, Errores y conteo de señales pendientes.
- **Historial Completo:** Tabla navegable con cada señal registrada en SQLite.
- **Botón `⚡ Analizar Ahora`:** Permite forzar un ciclo de análisis inmediato directamente desde el navegador.

---

## 📊 Base de Datos SQLite

Ubicada en `data/btc_scalping.db`, contiene 6 tablas relacionales:
1. `markets`: Metadatos y cotizaciones de los contratos de Kalshi.
2. `signals`: Registro inmutable de cada señal emitida, precio BTC, precio de contrato, indicadores JSON, score de confianza, strike de referencia y estado de evaluación.
3. `price_history`: Velas OHLCV históricas para 1m, 5m y 15m.
4. `signal_results`: Resultados finales de liquidación (`WIN`, `LOSS`, `VOID`).
5. `bot_logs`: Registro cronológico de eventos, advertencias y errores.
6. `settings`: Clave/valor de parámetros persistentes.

---

## 🚀 Guía de Instalación y Ejecución en macOS

### 1. Requisitos Previos
Tener instalado Python 3.11 o superior y Git en macOS:
```bash
python3 --version
git --version
```

### 2. Clonar e Ingresar al Directorio
```bash
git clone https://github.com/Beeshech93/kalshibot.git
cd kalshibot
```

### 3. Configurar Entorno Virtual
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurar Variables de Entorno
Copia la plantilla `.env.example` a `.env`:
```bash
cp .env.example .env
```
Edita `.env` con tus preferencias (especialmente las credenciales de Telegram si deseas recibir alertas):
```env
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
TELEGRAM_CHAT_ID=tu_chat_id
TELEGRAM_AUTHORIZED_USERS=tu_id_de_usuario
ANALYSIS_INTERVAL_MINUTES=15
MIN_CONFIDENCE_SCORE=60
MODE=SOLO_SEÑALES
```

### 5. Modos de Ejecución con `run.py`

#### A. Ejecutar Sistema Completo (Bot de Análisis + Dashboard Web Concurrente):
```bash
./venv/bin/python run.py
```
Abre tu navegador en: **`http://127.0.0.1:8080`**

#### B. Ejecutar Solo el Bot de Señales y Telegram (Headless):
```bash
./venv/bin/python run.py --bot
```

#### C. Ejecutar Solo el Dashboard Web:
```bash
./venv/bin/python run.py --dashboard
```

#### D. Ejecutar un Solo Ciclo Inmediato de Prueba y Salir:
```bash
./venv/bin/python run.py --once
```

### 6. Ejecución de Pruebas Automatizadas
Para validar todos los módulos matemáticos, lógica de señales y endpoints:
```bash
./venv/bin/python -m pytest tests/ -v
```

---

## 🍏 Configuración de Inicio Automático con `launchd` (macOS)

Para que **BTC SCALPING AI** se ejecute automáticamente como un servicio en segundo plano al encender tu Mac y se reinicie en caso de interrupción:

1. El archivo [`com.btcscalping.ai.plist`](file:///Users/wisly/BTC-Scalping-Bot/com.btcscalping.ai.plist) ya está configurado en el proyecto.
2. Cópialo a tu carpeta de LaunchAgents de macOS:
   ```bash
   cp com.btcscalping.ai.plist ~/Library/LaunchAgents/
   ```
3. Carga e inicia el servicio:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.btcscalping.ai.plist
   ```
4. Para consultar el estado o ver los logs generados por el servicio:
   ```bash
   tail -f logs/service_stdout.log
   tail -f logs/service_stderr.log
   ```
5. Para detener el servicio:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.btcscalping.ai.plist
   ```

---

## 📈 Integración con TradingView

1. Abre [TradingView](https://www.tradingview.com/).
2. Abre el **Pine Editor** en la parte inferior del gráfico.
3. Copia y pega el contenido completo de [`tradingview/btc_scalping.pine`](file:///Users/wisly/BTC-Scalping-Bot/tradingview/btc_scalping.pine).
4. Haz clic en **Add to Chart**.
5. Para configurar alertas webhook:
   - Crea una nueva alerta en TradingView con la condición `Alerta BUY (YES)` o `Alerta SELL (NO)`.
   - El script genera automáticamente payloads en formato JSON listos para ser consumidos por cualquier receptor HTTP webhook.

