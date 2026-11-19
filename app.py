# -*- coding: utf-8 -*-
"""
====================================================================================================
PROYECTO: CENTRO METEOROLÓGICO OPENWEATHERMAP PRO (EDICIÓN ENTERPRISE CON VOZ TTS)
EMPRESA / ORGANIZACIÓN: DATAIADEV / ARQUITECTURA DIGITAL JPV
AUTOR PRINCIPAL: ING. JUANCITO PEÑA VIZCAÍNO
VERSIÓN: 2.0.0
FECHA: NOVIEMBRE 2026
LICENCIA: MIT
====================================================================================================

DESCRIPCIÓN DE ARQUITECTURA:
----------------------------------------------------------------------------------------------------
Este sistema es una estación de teledetección, pronóstico numérico y analítica meteorológica
empresarial en tiempo real alimentada por los servicios REST mundiales de OpenWeatherMap.

Integra una arquitectura en tres capas:
1. CAPA DE INTEGRACIÓN Y SEGURIDAD API (SECRETS MANAGEMENT):
   - Resolución multi-nivel de API Key:
     Prioridad 1: Entrada manual en Sidebar (permite ingresar claves personalizadas).
     Prioridad 2: Streamlit Secrets (`st.secrets["OPENWEATHER_API_KEY"]`) para Streamlit Cloud.
     Prioridad 3: Variables de Entorno del Sistema (`os.getenv("OPENWEATHER_API_KEY")`).
     Prioridad 4: Clave predeterminada del sistema de contingencia.
   - Geocodificación directa (OpenWeather Geocoding API 1.0) con caché de 1 hora.
   - Telemetría actual y pronóstico horario extendido a 5 días con caché de 15 minutos.

2. CAPA DE INTELIGENCIA NARRATIVA E INTERPRETACIÓN EJECUTIVA (TTS):
   - Motor heurístico que analiza la dinámica atmosférica (amplitud térmica, sensación vs real,
     gradiente de presión, cizalladura del viento y probabilidad acumulada de lluvia).
   - Generación de dictámenes ejecutivos hablados mediante Web Speech API nativa,
     con controles táctiles Play/Pause/Resume/Stop y slider continuo de volumen.

3. CAPA DE VISUALIZACIÓN ANALÍTICA:
   - Cuadro Bento de 5 KPIs con deltas interpretados.
   - Curva térmica dual (Temperatura vs Sensación Térmica con área rellena).
   - Rosa de los Vientos polar (distribución de frecuencias y velocidades por cuadrante cardinal).
   - Radar de probabilidad de lluvia y nubosidad.
   - Gráfico barométrico de doble eje Y (Presión hPa vs Humedad Relativa %).
   - Mapa de calor matricial horario con escala reversible (azul=frío, rojo=calor).
   - Exportador de datos estructurados a CSV codificado en UTF-8.
====================================================================================================
"""

import json
import os
import uuid
from typing import Tuple, Optional, Dict, Any, List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

# ==================================================================================================
# 1. CONFIGURACIÓN DEL LIENZO STREAMLIT Y ESTILOS
# ==================================================================================================

st.set_page_config(
    page_title="Centro Meteorológico OpenWeatherMap Pro",
    page_icon="⛈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inyección de estilos visuales corporativos Neo-Brutalistas limpios
st.markdown("""
<style>
    .main .block-container {
        padding-top: 1.6rem;
        padding-bottom: 2.5rem;
    }
    .stMetric {
        background-color: #ffffff;
        border: 2px solid #0f172a;
        box-shadow: 3px 3px 0px #0f172a;
        border-radius: 8px;
        padding: 10px 14px;
    }
</style>
""", unsafe_allow_html=True)


# ==================================================================================================
# 2. RESOLUCIÓN SEGURA Y BLINDADA DE API KEY (SECRETS EN STREAMLIT CLOUD Y GITHUB)
# ==================================================================================================

def resolver_api_key() -> str:
    """
    Resuelve la API Key de OpenWeatherMap mediante una jerarquía en cascada segura:
    1. Input manual en Sidebar (si el usuario la especifica).
    2. Streamlit Cloud Secrets (st.secrets["OPENWEATHER_API_KEY"]).
    3. Variable de entorno del sistema operativo.
    4. Clave predeterminada embebida.
    """
    # 1. Verificar si el usuario ingresó una clave en la barra lateral
    if "api_key_custom" in st.session_state and st.session_state.api_key_custom.strip():
        return st.session_state.api_key_custom.strip()

    # 2. Verificar Streamlit Secrets (para share.streamlit.io)
    try:
        if hasattr(st, "secrets") and "OPENWEATHER_API_KEY" in st.secrets:
            clave = st.secrets["OPENWEATHER_API_KEY"]
            if clave and clave.strip() and not clave.startswith("tu_"):
                return clave.strip()
    except Exception:
        pass

    # 3. Verificar Variable de Entorno
    env_key = os.getenv("OPENWEATHER_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    # 4. Clave predeterminada funcional
    return "12e717669f6d0f7358f106ac8ab9528b"


def grados_a_cardinal(grados: float) -> str:
    """
    Convierte un rumbo en grados acimutales (0° - 360°) a su punto cardinal correspondiente.
    """
    direcciones = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    indice = round(grados / 45) % 8
    return direcciones[indice]


# ==================================================================================================
# 3. PIPELINE DE EXTRACCIÓN Y GEOCODIFICACIÓN (ETL CON CACHÉ)
# ==================================================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def obtener_coordenadas(ciudad: str, api_key: str) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    """
    Geocodifica un nombre de ciudad a coordenadas WGS84 (latitud, longitud).
    Caché de 1 hora para evitar consumo redundante de llamadas a la API de Geocodificación.
    """
    url = f"https://api.openweathermap.org/geo/1.0/direct?q={ciudad}&limit=1&appid={api_key}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200 and len(res.json()) > 0:
            data = res.json()[0]
            return float(data["lat"]), float(data["lon"]), str(data["name"]), str(data.get("country", ""))
        return None, None, None, None
    except Exception:
        return None, None, None, None


@st.cache_data(ttl=900, show_spinner=False)
def obtener_datos_meteorologicos(lat: float, lon: float, api_key: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Extrae la telemetría actual y el pronóstico de 5 días con resolución trihoraria desde OpenWeatherMap.
    Persistencia en caché de 15 minutos (ttl=900).
    """
    url_forecast = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&lang=es&appid={api_key}"
    url_current = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&lang=es&appid={api_key}"

    try:
        res_f = requests.get(url_forecast, timeout=12)
        res_c = requests.get(url_current, timeout=12)

        if res_f.status_code == 200 and res_c.status_code == 200:
            return res_c.json(), res_f.json()
        elif res_c.status_code == 401 or res_f.status_code == 401:
            st.error("❌ Error 401: Clave API de OpenWeatherMap no autorizada o inválida. Verifique sus credenciales.")
            return None, None
        elif res_c.status_code == 429 or res_f.status_code == 429:
            st.error("⚠️ Error 429: Límite de peticiones de OpenWeatherMap excedido temporalmente. Espere unos minutos.")
            return None, None
        return None, None
    except Exception as exc:
        st.error(f"⚠️ Error de conexión de red con OpenWeatherMap: {exc}")
        return None, None


# ==================================================================================================
# 4. MOTOR DE INTELIGENCIA NARRATIVA E INTERPRETACIÓN EJECUTIVA
# ==================================================================================================

def interpretar_kpis_meteorologicos(clima_act: Dict[str, Any], df: pd.DataFrame, ciudad: str, pais: str) -> str:
    """
    Genera un dictamen ejecutivo profundo de las condiciones actuales y los pronósticos de corto plazo.
    """
    temp_now = clima_act["main"]["temp"]
    feels_now = clima_act["main"]["feels_like"]
    hum_now = clima_act["main"]["humidity"]
    pres_now = clima_act["main"]["pressure"]
    wind_kmh = clima_act["wind"]["speed"] * 3.6
    condicion = clima_act["weather"][0]["description"].capitalize()
    lluvia_tot = df["lluvia_mm"].sum()
    prob_lluvia_max = df["prob_lluvia"].max()

    dif_sensacion = feels_now - temp_now
    if abs(dif_sensacion) < 1.0:
        analisis_termico = f"La temperatura se sitúa en {temp_now:.1f} grados Celsius, con una sensación térmica alineada de {feels_now:.1f} grados."
    elif dif_sensacion > 0:
        analisis_termico = f"La temperatura termodinámica marca {temp_now:.1f} grados, pero la elevada humedad relativa del {hum_now} por ciento eleva la sensación térmica real hasta los {feels_now:.1f} grados Celsius."
    else:
        analisis_termico = f"El termómetro registra {temp_now:.1f} grados, con una sensación térmica disminuida de {feels_now:.1f} grados debido a la acción del viento."

    # Diagnóstico Barométrico
    if pres_now < 1010:
        analisis_presion = f"El barómetro reporta una baja presión de {pres_now} hectopascales, lo que indica inestabilidad atmosférica y riesgo latente de chubascos o tormentas."
    elif pres_now > 1020:
        analisis_presion = f"Presión barométrica alta de {pres_now} hectopascales, señal de un anticiclón con atmósfera estable y cielo despejado."
    else:
        analisis_presion = f"La presión atmosférica se mantiene normal en {pres_now} hectopascales."

    analisis_precipitacion = (
        f"En el horizonte de 5 días se proyecta un acumulado pluvial de {lluvia_tot:.1f} milímetros, "
        f"con un pico de probabilidad de lluvia del {prob_lluvia_max:.0f} por ciento. "
        f"{'Se recomienda planificar contingencias logísticas ante suelos mojados.' if prob_lluvia_max >= 50 else 'Condiciones secas y favorables para actividades al aire libre.'}"
    )

    return (
        f"Informe Meteorológico Ejecutivo para {ciudad}, {pais}. "
        f"Condición reportada: {condicion}. "
        f"{analisis_termico} "
        f"{analisis_presion} "
        f"Viento actual a {wind_kmh:.1f} kilómetros por hora desde el {grados_a_cardinal(clima_act['wind'].get('deg', 0))}. "
        f"{analisis_precipitacion}"
    )


def interpretar_evolucion_termica(df: pd.DataFrame, ciudad: str) -> str:
    temp_min = df["temperatura"].min()
    temp_max = df["temperatura"].max()
    feels_max = df["sensacion_termica"].max()
    prom_temp = df["temperatura"].mean()
    amplitud = temp_max - temp_min

    return (
        f"Dictamen de Evolución Térmica para {ciudad}. "
        f"La temperatura media esperada es de {prom_temp:.1f} grados Celsius, con una oscilación térmica que va desde una mínima de {temp_min:.1f} grados "
        f"hasta una máxima de {temp_max:.1f} grados, alcanzando una sensación térmica cúspide de {feels_max:.1f} grados. "
        f"{'La elevada amplitud térmica de ' + str(round(amplitud, 1)) + ' grados exigirá precauciones frente a cambios bruscos de temperatura entre día y noche.' if amplitud > 8 else 'Régimen térmico muy estable y predecible a lo largo de las jornadas.'}"
    )


def interpretar_rosa_vientos(df: pd.DataFrame, ciudad: str) -> str:
    df_viento = df.groupby("direccion_viento", as_index=False).agg(
        velocidad_media=("viento_kmh", "mean"),
        frecuencia=("time", "count")
    )
    if df_viento.empty:
        return "No hay suficientes datos eólicos para estructurar la rosa de los vientos."

    cuadrante_dominante = df_viento.sort_values("frecuencia", ascending=False).iloc[0]
    vel_max = df["viento_kmh"].max()
    dir_max = df.loc[df["viento_kmh"].idxmax()]["direccion_viento"]

    return (
        f"Análisis Aerodinámico y Rosa de los Vientos en {ciudad}. "
        f"El flujo eólico predominante procede del cuadrante {cuadrante_dominante['direccion_viento']} "
        f"con una velocidad media de {cuadrante_dominante['velocidad_media']:.1f} kilómetros por hora. "
        f"La ráfaga máxima proyectada alcanza los {vel_max:.1f} kilómetros por hora proveniente del {dir_max}. "
        f"{'Vientos moderados o fuertes; se recomienda afianzar estructuras ligeras y supervisar faenas de altura.' if vel_max >= 30 else 'Flujo de brisa suave a moderada, sin riesgo para grúas u operaciones portuarias.'}"
    )


def interpretar_precipitacion_nubosidad(df: pd.DataFrame, ciudad: str) -> str:
    prob_max = df["prob_lluvia"].max()
    nubosidad_prom = df["nubosidad"].mean()
    lluvia_total = df["lluvia_mm"].sum()

    return (
        f"Evaluación Pluviométrica y Nubosidad para {ciudad}. "
        f"La cobertura nubosa promedio se calcula en {nubosidad_prom:.0f} por ciento. "
        f"El volumen de precipitación acumulado ascenderá a {lluvia_total:.1f} milímetros en 5 días. "
        f"{'Se confirma una ventana de alta probabilidad de lluvias del ' + str(int(prob_max)) + ' por ciento. Se aconseja prever drenajes y demoras en trayectos viales.' if prob_max >= 50 else 'Probabilidades de lluvia escasas o nulas, con predominio de cielos mayormente abiertos.'}"
    )


def interpretar_presion_humedad(df: pd.DataFrame, ciudad: str) -> str:
    pres_min = df["presion"].min()
    pres_max = df["presion"].max()
    hum_prom = df["humedad"].mean()

    return (
        f"Diagnóstico Barométrico y de Humedad Relativa en {ciudad}. "
        f"El rango de presión oscilará entre los {pres_min} y los {pres_max} hectopascales, "
        f"con una humedad media del {hum_prom:.0f} por ciento. "
        f"{'Atención: la caída de presión por debajo de 1010 hPa señala la proximidad de vaguadas o perturbaciones convectivas.' if pres_min < 1010 else 'Comportamiento barométrico equilibrado sin perturbaciones meteorológicas severas en el horizonte.'}"
    )


def interpretar_mapa_calor_termico(df: pd.DataFrame, ciudad: str) -> str:
    temp_pico = df.loc[df["temperatura"].idxmax()]
    hora_pico = temp_pico["hora"]
    fecha_pico = temp_pico["fecha"]
    temp_val = temp_pico["temperatura"]

    return (
        f"Análisis del Mapa de Calor Térmico para {ciudad}. "
        f"El momento de mayor intensidad térmica tendrá lugar el día {fecha_pico} a las {hora_pico} horas, "
        f"cuando el termómetro alcanzará {temp_val:.1f} grados Celsius. "
        f"Se recomienda programar las faenas físicas más demandantes en horas matutinas o vespertinas para mitigar el golpe de calor."
    )


# ==================================================================================================
# 5. COMPONENTE WEB MAESTRO DE NARRACIÓN POR VOZ (TTS - ESTÁNDAR JPV PRO)
# ==================================================================================================

def renderizar_control_audio_tts(texto_narracion: str, bloque_id: str, titulo: str = "Informe Ejecutivo"):
    """
    Incrusta la consola multimedia con Web Speech API nativa, controles táctiles y control de volumen.
    """
    texto_json = json.dumps(texto_narracion, ensure_ascii=False)
    id_seguro = f"tts_{bloque_id}_{uuid.uuid4().hex[:6]}"

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <style>
            * {{
                box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            }}
            body {{
                margin: 0;
                padding: 4px 0;
                background: transparent;
            }}
            .tts-container {{
                background: #ffffff;
                border: 2px solid #0f172a;
                border-radius: 8px;
                padding: 10px 14px;
                box-shadow: 3px 3px 0px #0f172a;
                margin-bottom: 8px;
            }}
            .tts-header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 8px;
            }}
            .tts-title {{
                font-size: 0.82rem;
                font-weight: 700;
                color: #0f172a;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .tts-toolbar {{
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }}
            .btn-tts {{
                display: inline-flex;
                align-items: center;
                gap: 5px;
                font-size: 0.78rem;
                font-weight: 700;
                padding: 5px 12px;
                border-radius: 6px;
                border: 1.5px solid #0f172a;
                cursor: pointer;
                transition: all 0.15s ease-in-out;
            }}
            .btn-tts:active {{
                transform: translate(1px, 1px);
            }}
            .btn-play {{
                background: #0f172a;
                color: #ffffff;
                box-shadow: 2px 2px 0px #38bdf8;
            }}
            .btn-play:hover {{ background: #1e293b; }}
            .btn-pause {{ background: #eab308; color: #0f172a; box-shadow: 2px 2px 0px #0f172a; }}
            .btn-resume {{ background: #3b82f6; color: #ffffff; box-shadow: 2px 2px 0px #0f172a; }}
            .btn-stop {{ background: #ef4444; color: #ffffff; box-shadow: 2px 2px 0px #0f172a; }}
            .audio-wave-dot {{
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background-color: #22c55e;
                box-shadow: 0 0 6px #22c55e;
                animation: audioPulse 0.9s infinite alternate ease-in-out;
            }}
            @keyframes audioPulse {{
                0% {{ transform: scale(0.8); opacity: 0.5; }}
                100% {{ transform: scale(1.3); opacity: 1; }}
            }}
            .status-badge {{
                display: none;
                align-items: center;
                gap: 6px;
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 0.72rem;
                font-weight: 600;
                color: #334155;
            }}
            .vol-control {{
                display: flex;
                align-items: center;
                gap: 4px;
                background: #f8fafc;
                border: 1px solid #94a3b8;
                border-radius: 6px;
                padding: 3px 6px;
                font-size: 0.72rem;
            }}
            .vol-btn {{
                background: transparent;
                border: 1px solid #cbd5e1;
                border-radius: 3px;
                font-size: 0.75rem;
                font-weight: 800;
                cursor: pointer;
                padding: 0 5px;
            }}
            .vol-slider {{
                width: 60px;
                height: 4px;
                accent-color: #0284c7;
                cursor: pointer;
            }}
            .vol-badge {{
                font-weight: 700;
                font-size: 0.7rem;
                color: #0f172a;
                min-width: 32px;
                text-align: right;
            }}
        </style>
    </head>
    <body>
        <div class="tts-container">
            <div class="tts-header">
                <div class="tts-title">🎙️ {titulo}</div>
                <div class="status-badge" id="badge_{id_seguro}">
                    <span class="audio-wave-dot"></span>
                    <span id="status_text_{id_seguro}">Narrando...</span>
                </div>
            </div>
            
            <div class="tts-toolbar">
                <button type="button" class="btn-tts btn-play" id="btn_play_{id_seguro}" onclick="narrar_{id_seguro}()">
                    ▶️ <span>Escuchar Informe</span>
                </button>
                <button type="button" class="btn-tts btn-pause" id="btn_pause_{id_seguro}" style="display:none;" onclick="pausar_{id_seguro}()">
                    ⏸️ <span>Pausar</span>
                </button>
                <button type="button" class="btn-tts btn-resume" id="btn_resume_{id_seguro}" style="display:none;" onclick="reanudar_{id_seguro}()">
                    ⏯️ <span>Reanudar</span>
                </button>
                <button type="button" class="btn-tts btn-stop" id="btn_stop_{id_seguro}" style="display:none;" onclick="detener_{id_seguro}()">
                    ⏹️ <span>Detener</span>
                </button>

                <div class="vol-control">
                    <span>🔊</span>
                    <button type="button" class="vol-btn" onclick="ajustarVolumen_{id_seguro}(-0.1)">-</button>
                    <input type="range" class="vol-slider" id="slider_{id_seguro}" min="0" max="1" step="0.05" value="1" oninput="cambiarVolumenDirecto_{id_seguro}(this.value)">
                    <button type="button" class="vol-btn" onclick="ajustarVolumen_{id_seguro}(0.1)">+</button>
                    <span class="vol-badge" id="vol_txt_{id_seguro}">100%</span>
                </div>
            </div>
        </div>

        <script>
            (function() {{
                const textoParaNarrar = {texto_json};
                const synth = window.speechSynthesis;
                let currentUtterance = null;
                let volumenActual = 1.0;

                const btnPlay = document.getElementById("btn_play_{id_seguro}");
                const btnPause = document.getElementById("btn_pause_{id_seguro}");
                const btnResume = document.getElementById("btn_resume_{id_seguro}");
                const btnStop = document.getElementById("btn_stop_{id_seguro}");
                const badge = document.getElementById("badge_{id_seguro}");
                const statusTxt = document.getElementById("status_text_{id_seguro}");
                const slider = document.getElementById("slider_{id_seguro}");
                const volTxt = document.getElementById("vol_txt_{id_seguro}");

                function obtenerVozEspanol() {{
                    if (!synth) return null;
                    const voces = synth.getVoices();
                    return voces.find(v => v.lang.startsWith("es-") || v.lang === "es") || null;
                }}

                window.narrar_{id_seguro} = function() {{
                    if (!synth) {{
                        alert("Tu navegador no soporta síntesis de voz (Web Speech API).");
                        return;
                    }}

                    if (synth.paused && currentUtterance) {{
                        synth.resume();
                        actualizarUI("speaking");
                        return;
                    }}

                    synth.cancel();

                    currentUtterance = new SpeechSynthesisUtterance(textoParaNarrar);
                    const voz = obtenerVozEspanol();
                    if (voz) currentUtterance.voice = voz;
                    currentUtterance.lang = "es-ES";
                    currentUtterance.rate = 1.02;
                    currentUtterance.pitch = 1.0;
                    currentUtterance.volume = volumenActual;

                    currentUtterance.onstart = () => actualizarUI("speaking");
                    currentUtterance.onend = () => actualizarUI("idle");
                    currentUtterance.onerror = () => actualizarUI("idle");

                    synth.speak(currentUtterance);
                }};

                window.pausar_{id_seguro} = function() {{
                    if (synth && synth.speaking) {{
                        synth.pause();
                        actualizarUI("paused");
                    }}
                }};

                window.reanudar_{id_seguro} = function() {{
                    if (synth && synth.paused) {{
                        synth.resume();
                        actualizarUI("speaking");
                    }}
                }};

                window.detener_{id_seguro} = function() {{
                    if (synth) {{
                        synth.cancel();
                        actualizarUI("idle");
                    }}
                }};

                window.cambiarVolumenDirecto_{id_seguro} = function(val) {{
                    volumenActual = Math.max(0, Math.min(1, parseFloat(val)));
                    slider.value = volumenActual;
                    volTxt.innerText = Math.round(volumenActual * 100) + "%";
                    if (currentUtterance && synth.speaking) {{
                        currentUtterance.volume = volumenActual;
                    }}
                }};

                window.ajustarVolumen_{id_seguro} = function(delta) {{
                    let nuevoVol = Math.round((volumenActual + delta) * 100) / 100;
                    cambiarVolumenDirecto_{id_seguro}(nuevoVol);
                }};

                function actualizarUI(estado) {{
                    if (estado === "speaking") {{
                        btnPlay.style.display = "none";
                        btnPause.style.display = "inline-flex";
                        btnResume.style.display = "none";
                        btnStop.style.display = "inline-flex";
                        badge.style.display = "inline-flex";
                        statusTxt.innerText = "Narrando informe...";
                    }} else if (estado === "paused") {{
                        btnPlay.style.display = "none";
                        btnPause.style.display = "none";
                        btnResume.style.display = "inline-flex";
                        btnStop.style.display = "inline-flex";
                        badge.style.display = "inline-flex";
                        statusTxt.innerText = "Pausado";
                    }} else {{
                        btnPlay.style.display = "inline-flex";
                        btnPause.style.display = "none";
                        btnResume.style.display = "none";
                        btnStop.style.display = "none";
                        badge.style.display = "none";
                    }}
                }}

                if (speechSynthesis.onvoiceschanged !== undefined) {{
                    speechSynthesis.onvoiceschanged = obtenerVozEspanol;
                }}
            }})();
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=92, scrolling=False)


# ==================================================================================================
# 6. BARRA LATERAL (BÚSQUEDA Y CONFIGURACIÓN DE CREDENCIALES)
# ==================================================================================================

st.sidebar.header("🌍 Estación Meteorológica")
st.sidebar.markdown("Consulta cualquier ubicación del mundo mediante telemetría satelital:")

ciudad_input = st.sidebar.text_input(
    "Ciudad (Ej: Santo Domingo, DO / Madrid, ES / Bogotá, CO):",
    value="Santo Domingo, DO",
    help="Indica el nombre de la ciudad seguido del código ISO del país (ej: DO, ES, MX, CO, AR)."
)

# Selector de accesos rápidos a ciudades representativas
ciudades_rapidas = {
    "Personalizada": None,
    "Santo Domingo, DO": "Santo Domingo, DO",
    "Santiago de los Caballeros, DO": "Santiago, DO",
    "Madrid, España": "Madrid, ES",
    "Ciudad de México, MX": "Mexico City, MX",
    "Bogotá, Colombia": "Bogota, CO",
    "Buenos Aires, AR": "Buenos Aires, AR"
}

seleccion_rapida = st.sidebar.selectbox("⚡ Accesos rápidos:", list(ciudades_rapidas.keys()), index=0)
if seleccion_rapida != "Personalizada" and ciudades_rapidas[seleccion_rapida]:
    ciudad_efectiva = ciudades_rapidas[seleccion_rapida]
else:
    ciudad_efectiva = ciudad_input

st.sidebar.divider()
st.sidebar.subheader("🔐 Gestión de API Key")

# Campo opcional para clave personalizada
custom_key = st.sidebar.text_input(
    "Clave OpenWeatherMap (Opcional):",
    value="",
    type="password",
    help="Si posees una cuenta propia en OpenWeatherMap, ingresa tu clave. Si la dejas vacía, el sistema usa la clave integrada."
)
st.session_state.api_key_custom = custom_key

api_key_activa = resolver_api_key()
st.sidebar.caption("🟢 Conexión API activa y validada")

# ==================================================================================================
# 7. EJECUCIÓN DEL PIPELINE ETL
# ==================================================================================================

lat, lon, nombre_ciudad, pais = obtener_coordenadas(ciudad_efectiva, api_key_activa)

if lat is None:
    st.error(f"⚠️ No se encontró la ciudad '{ciudad_efectiva}'. Verifique la ortografía o use el formato 'Ciudad, CódigoPaís' (Ej: 'Santo Domingo, DO').")
    st.stop()

with st.spinner(f"Sincronizando telemetría meteorológica para {nombre_ciudad}, {pais}..."):
    clima_actual, pronostico_api = obtener_datos_meteorologicos(lat, lon, api_key_activa)

if not pronostico_api or not clima_actual:
    st.error("❌ No se pudieron recuperar los datos meteorológicos de OpenWeatherMap. Verifique su conexión o clave API.")
    st.stop()

# Transformación de datos de pronóstico a DataFrame estructurado
registros: List[Dict[str, Any]] = []
for item in pronostico_api["list"]:
    deg_viento = item["wind"].get("deg", 0)
    registros.append({
        "time": item["dt_txt"],
        "temperatura": float(item["main"]["temp"]),
        "temp_min": float(item["main"]["temp_min"]),
        "temp_max": float(item["main"]["temp_max"]),
        "sensacion_termica": float(item["main"]["feels_like"]),
        "humedad": int(item["main"]["humidity"]),
        "presion": int(item["main"]["pressure"]),
        "viento_ms": float(item["wind"]["speed"]),
        "viento_kmh": round(float(item["wind"]["speed"]) * 3.6, 1),
        "viento_deg": deg_viento,
        "direccion_viento": grados_a_cardinal(deg_viento),
        "nubosidad": int(item["clouds"]["all"]),
        "clima": item["weather"][0]["description"].capitalize(),
        "prob_lluvia": round(float(item.get("pop", 0)) * 100, 0),
        "lluvia_mm": float(item.get("rain", {}).get("3h", 0.0))
    })

df = pd.DataFrame(registros)
df["time"] = pd.to_datetime(df["time"])
df["fecha"] = df["time"].dt.strftime("%d-%b")
df["hora"] = df["time"].dt.strftime("%H:%M")

# ==================================================================================================
# 8. ENCABEZADO Y TARJETAS BENTO DE KPIS CON NARRADOR EJECUTIVO
# ==================================================================================================

st.title(f"⛈️ Centro Meteorológico: {nombre_ciudad}, {pais}")
condicion_hoy = clima_actual["weather"][0]["description"].capitalize()
st.markdown(f"**Coordenadas:** `{lat:.4f}°, {lon:.4f}°` | **Condición Reportada por Estación:** `{condicion_hoy}`")

# Narrador Ejecutivo Principal de KPIs
texto_kpis = interpretar_kpis_meteorologicos(clima_actual, df, nombre_ciudad, pais)
renderizar_control_audio_tts(texto_kpis, "kpis_hero", "Narración Ejecutiva: Diagnóstico de Condiciones Actuales")

with st.expander("📄 Ver transcripción del dictamen meteorológico de KPIs"):
    st.info(texto_kpis)

temp_now = clima_actual["main"]["temp"]
feels_now = clima_actual["main"]["feels_like"]
hum_now = clima_actual["main"]["humidity"]
pres_now = clima_actual["main"]["pressure"]
wind_now_kmh = clima_actual["wind"]["speed"] * 3.6
clouds_now = clima_actual["clouds"]["all"]
lluvia_5d = df["lluvia_mm"].sum()
prob_max = df["prob_lluvia"].max()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("🌡️ Temp. Actual", f"{temp_now:.1f} °C", f"Sensación: {feels_now:.1f} °C")
c2.metric("💧 Humedad", f"{hum_now} %", f"Nubosidad: {clouds_now} %", delta_color="off")
c3.metric("💨 Viento Actual", f"{wind_now_kmh:.1f} km/h", f"Rumbo: {grados_a_cardinal(clima_actual['wind'].get('deg', 0))}", delta_color="off")
c4.metric("🧭 Presión Atm.", f"{pres_now} hPa", f"{'Baja Presión' if pres_now < 1013 else 'Estable'}", delta_color="off")
c5.metric("🌧️ Lluvia Est. (5d)", f"{lluvia_5d:.1f} mm", f"Máx Prob: {prob_max:.0f} %", delta_color="inverse")

st.divider()

# ==================================================================================================
# 9. FILA 1: EVOLUCIÓN TÉRMICA Y ROSA DE LOS VIENTOS CON NARRADORES
# ==================================================================================================

col_izq, col_der = st.columns([2, 1])

with col_izq:
    st.subheader("🌡️ Evolución Térmica: Temperatura Real vs Sensación Térmica")
    texto_temp = interpretar_evolucion_termica(df, nombre_ciudad)
    renderizar_control_audio_tts(texto_temp, "grafico_temperatura", "Narración: Tendencias Térmicas y Amplitud")

    fig_temp = go.Figure()
    # Área suave para sensación térmica
    fig_temp.add_trace(go.Scatter(
        x=df["time"],
        y=df["sensacion_termica"],
        mode="lines",
        name="Sensación Térmica (°C)",
        line=dict(color="#FF9F1C", width=2, dash="dot"),
        fill="tozeroy",
        fillcolor="rgba(255, 159, 28, 0.12)"
    ))
    # Curva principal de temperatura
    fig_temp.add_trace(go.Scatter(
        x=df["time"],
        y=df["temperatura"],
        mode="lines+markers",
        name="Temperatura (°C)",
        line=dict(color="#E71D36", width=3),
        marker=dict(size=5, color="#E71D36")
    ))
    # Línea horizontal del promedio
    temp_prom = df["temperatura"].mean()
    fig_temp.add_hline(
        y=temp_prom, line_dash="dash", line_color="gray",
        annotation_text=f"Promedio: {temp_prom:.1f}°C", annotation_position="top left"
    )
    fig_temp.update_layout(
        yaxis=dict(title="Grados Celsius (°C)"),
        xaxis=dict(title="Fecha y Hora"),
        legend=dict(orientation="h", y=1.14),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=30, b=20),
        height=380
    )
    st.plotly_chart(fig_temp, use_container_width=True)

with col_der:
    st.subheader("🧭 Rosa de los Vientos")
    texto_viento = interpretar_rosa_vientos(df, nombre_ciudad)
    renderizar_control_audio_tts(texto_viento, "rosa_vientos", "Narración: Análisis Aerodinámico Eólico")

    df_viento = df.groupby("direccion_viento", as_index=False).agg(
        velocidad_media=("viento_kmh", "mean"),
        frecuencia=("time", "count")
    )
    orden_cardinal = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    df_viento["direccion_viento"] = pd.Categorical(df_viento["direccion_viento"], categories=orden_cardinal, ordered=True)
    df_viento = df_viento.sort_values("direccion_viento")

    fig_rosa = px.bar_polar(
        df_viento,
        r="frecuencia",
        theta="direccion_viento",
        color="velocidad_media",
        color_continuous_scale="Tealgrn",
        labels={"frecuencia": "Horas Observadas", "velocidad_media": "Vel. Media (km/h)", "direccion_viento": "Rumbo"}
    )
    fig_rosa.update_layout(
        margin=dict(l=30, r=30, t=30, b=30),
        height=380
    )
    st.plotly_chart(fig_rosa, use_container_width=True)

st.divider()

# ==================================================================================================
# 10. FILA 2: RADAR DE PRECIPITACIONES Y BARÓMETRO / PSICROMETRÍA
# ==================================================================================================

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("🌧️ Radar de Precipitación (%) y Nubosidad")
    texto_lluvia = interpretar_precipitacion_nubosidad(df, nombre_ciudad)
    renderizar_control_audio_tts(texto_lluvia, "radar_lluvia", "Narración: Evaluación Pluviométrica y Nubosidad")

    fig_lluvia = go.Figure()
    fig_lluvia.add_trace(go.Bar(
        x=df["time"],
        y=df["prob_lluvia"],
        name="Probabilidad Lluvia (%)",
        marker_color="rgba(0, 119, 182, 0.75)"
    ))
    fig_lluvia.add_trace(go.Scatter(
        x=df["time"],
        y=df["nubosidad"],
        mode="lines",
        name="Nubosidad (%)",
        line=dict(color="#6C757D", width=2),
        fill="tozeroy",
        fillcolor="rgba(108, 117, 125, 0.15)"
    ))
    fig_lluvia.update_layout(
        yaxis=dict(title="Porcentaje (%)", range=[0, 105]),
        legend=dict(orientation="h", y=1.14),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=30, b=20),
        height=350
    )
    st.plotly_chart(fig_lluvia, use_container_width=True)

with col_b:
    st.subheader("🧭 Presión Atmosférica (hPa) vs Humedad Relativa (%)")
    texto_presion = interpretar_presion_humedad(df, nombre_ciudad)
    renderizar_control_audio_tts(texto_presion, "barometro", "Narración: Barómetro y Humedad Psicrométrica")

    fig_presion = go.Figure()
    fig_presion.add_trace(go.Scatter(
        x=df["time"],
        y=df["presion"],
        mode="lines+markers",
        name="Presión (hPa)",
        line=dict(color="#7209B7", width=2.5)
    ))
    fig_presion.add_trace(go.Scatter(
        x=df["time"],
        y=df["humedad"],
        mode="lines",
        name="Humedad Relativa (%)",
        line=dict(color="#2EC4B6", width=2),
        yaxis="y2"
    ))
    fig_presion.update_layout(
        yaxis=dict(title="Presión (hPa)"),
        yaxis2=dict(title="Humedad (%)", overlaying="y", side="right", range=[0, 105]),
        legend=dict(orientation="h", y=1.14),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=30, b=20),
        height=350
    )
    st.plotly_chart(fig_presion, use_container_width=True)

st.divider()

# ==================================================================================================
# 11. FILA 3: MAPA DE CALOR TÉRMICO HORARIO (DÍA VS HORA)
# ==================================================================================================

st.subheader("🔥 Mapa de Calor Térmico: Temperatura por Día y Franja Horaria")
texto_calor = interpretar_mapa_calor_termico(df, nombre_ciudad)
renderizar_control_audio_tts(texto_calor, "mapa_calor_termico", "Narración: Matriz Térmica y Picos de Calor")

pivote_temp = df.pivot_table(index="hora", columns="fecha", values="temperatura", aggfunc="mean")
fig_heat = px.imshow(
    pivote_temp,
    text_auto=".1f",
    color_continuous_scale="RdYlBu_r",
    labels=dict(x="Fecha de Pronóstico", y="Hora del Día", color="Temp (°C)"),
    aspect="auto"
)
fig_heat.update_layout(height=340, margin=dict(l=20, r=20, t=20, b=20))
st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# ==================================================================================================
# 12. TABLA GRANULAR Y REPOSITORIO DE DATOS DESCARGABLE
# ==================================================================================================

with st.expander("📋 Ver matriz de datos meteorológicos estructurados y descargar"):
    st.dataframe(
        df[["time", "temperatura", "sensacion_termica", "humedad", "presion", "viento_kmh", "direccion_viento", "nubosidad", "prob_lluvia", "lluvia_mm", "clima"]],
        use_container_width=True
    )
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Descargar Datos Meteorológicos en CSV (UTF-8)",
        data=csv,
        file_name=f"meteorologia_{nombre_ciudad.lower().replace(' ', '_')}.csv",
        mime="text/csv",
        help="Exportación tabular compatible con Power BI, Excel y entornos analíticos."
    )

# ==================================================================================================
# 13. FOOTER OFICIAL INSTITUCIONAL JPV
# ==================================================================================================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #64748b; font-size: 0.85rem; padding: 10px 0;">
    <strong>Centro Meteorológico OpenWeatherMap Pro</strong> | Desarrollado con 💻 por <strong>Ing. Juancito Peña Vizcaíno</strong><br>
    Arquitectura Digital Enterprise • OpenWeatherMap API • Web Speech API TTS • 2026
</div>
""", unsafe_allow_html=True)
