import os
import subprocess
import time
import requests
from playwright.sync_api import sync_playwright

def main():
    base_dir = r"C:\Users\User\Desktop\CARPETA DE TRABAJO DE ANTIGRAVITY CLI-JPV\centro_meteorologico_openweather"
    docs_dir = os.path.join(base_dir, "docs", "screenshots")
    os.makedirs(docs_dir, exist_ok=True)
    python_exe = os.path.join(base_dir, ".venv", "Scripts", "python.exe")
    
    print("[1] Iniciando servidor Streamlit en puerto 8502 para no colisionar...")
    cmd_streamlit = [python_exe, "-m", "streamlit", "run", "app.py", "--server.headless=true", "--server.port=8502"]
    proc = subprocess.Popen(cmd_streamlit, cwd=base_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    url = "http://localhost:8502"
    for i in range(30):
        time.sleep(1)
        try:
            r = requests.get(url, timeout=1)
            if r.status_code == 200:
                print(f"[2] Servidor Streamlit activo tras {i+1}s.")
                break
        except Exception:
            pass
            
    # Dar tiempo a que OpenWeatherMap responda y Plotly renderice
    time.sleep(6)
    
    print("[3] Conectando Playwright con Microsoft Edge nativo...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1.25)
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        time.sleep(5)
        
        # 1. Portada, KPIs y Narrador
        print("[4] Captura 1: Portada, KPIs y Narrador...")
        cap1 = os.path.join(docs_dir, "01_hero_kpis_narrador.png")
        page.screenshot(path=cap1)
        
        # 2. Evolución Térmica y Rosa de los Vientos
        print("[5] Scroll y Captura 2: Evolución Térmica y Rosa de los Vientos...")
        page.evaluate("window.scrollTo(0, 480);")
        time.sleep(2)
        cap2 = os.path.join(docs_dir, "02_evolucion_termica_rosa_vientos.png")
        page.screenshot(path=cap2)
        
        # 3. Radar de Lluvia, Barómetro y Heatmap Térmico
        print("[6] Scroll y Captura 3: Radar de Lluvia, Barómetro y Heatmap...")
        page.evaluate("window.scrollTo(0, 1050);")
        time.sleep(2)
        cap3 = os.path.join(docs_dir, "03_radar_lluvia_barometro_heatmap.png")
        page.screenshot(path=cap3)
        
        # 4. Panorámica Completa
        print("[7] Captura Panorámica Completa...")
        full_cap = os.path.join(docs_dir, "00_dashboard_completo.png")
        page.screenshot(path=full_cap, full_page=True)
        
        browser.close()
        print("[8] Capturas guardadas en docs/screenshots/")
        
    print("[9] Cerrando proceso Streamlit...")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
    print("[OK] Proceso completado exitosamente.")

if __name__ == "__main__":
    main()
