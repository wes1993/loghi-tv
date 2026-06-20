import io
import os
import re
import requests
import time
from PIL import Image, ImageDraw

USER_RUN = False  # Imposta su False se vuoi che lo script faccia tutto da solo senza fermarsi

# 🛠️ IMPOSTA QUI L'ORDINE DELLE CATEGORIE COME PREFERISCI!
# Le categorie non presenti in questa lista verranno accodate automaticamente alla fine.
ORDINE_CATEGORIE = ["FILM - SERIE TV", "RAI", "NEWS"]


def crea_sfondo_sfumato(dimensione):
    """Genera la base quadrata con la sfumatura radiale scura in stile Stremio"""
    sfondo = Image.new("RGBA", (dimensione, dimensione))
    draw = ImageDraw.Draw(sfondo)
    
    colore_centro = (24, 21, 43, 255)   # Viola/Blu scuro centrale
    colore_bordo = (11, 9, 19, 255)     # Quasi nero ai bordi
    
    raggio_massimo = int((dimensione ** 2 + dimensione ** 2) ** 0.5) / 2
    for y in range(dimensione):
        for x in range(dimensione):
            distanza_centro = ((x - dimensione/2)**2 + (y - dimensione/2)**2)**0.5
            fattore = min(distanza_centro / raggio_massimo, 1.0)
            
            r = int(colore_centro[0] + (colore_bordo[0] - colore_centro[0]) * fattore)
            g = int(colore_centro[1] + (colore_bordo[1] - colore_centro[1]) * fattore)
            b = int(colore_centro[2] + (colore_bordo[2] - colore_centro[2]) * fattore)
            
            draw.point((x, y), fill=(r, g, b, 255))
    return sfondo


def ordina_categorie(categorie_mappate, ordine_richiesto):
    """
    Ordina il dizionario delle categorie. Se ordine_richiesto è vuoto, 
    mantiene l'ordine originale di inserimento.
    """
    if not ordine_richiesto:
        return categorie_mappate

    categorie_ordinate = {}
    
    # 1. Inserisce prima le categorie nell'ordine richiesto dall'utente
    for cat in ordine_richiesto:
        if cat in categorie_mappate:
            categorie_ordinate[cat] = categorie_mappate[cat]
            
    # 2. Accoda tutte le altre categorie rimaste fuori dall'elenco
    for cat in categorie_mappate:
        if cat not in categorie_ordinate:
            categorie_ordinate[cat] = categorie_mappate[cat]
            
    return categorie_ordinate


def scarica_e_processa_logo(url, path_salvataggio, dimensione_quadrato):
    """Scarica il logo dall'URL, lo centra sullo sfondo sfumato e lo salva"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    logo_originale = Image.open(io.BytesIO(response.content)).convert("RGBA")
    
    sfondo_sfumato = crea_sfondo_sfumato(dimensione_quadrato)
    
    larghezza_orig, altezza_orig = logo_originale.size
    nuova_larghezza = int(dimensione_quadrato * 0.85)
    nuova_altezza = int((altezza_orig * nuova_larghezza) / larghezza_orig)
    
    if nuova_altezza > dimensione_quadrato * 0.85:
        nuova_altezza = int(dimensione_quadrato * 0.85)
        nuova_larghezza = int((larghezza_orig * nuova_altezza) / altezza_orig)
        
    logo_ridimensionato = logo_originale.resize((nuova_larghezza, nuova_altezza), Image.Resampling.LANCZOS)
    
    pos_x = (dimensione_quadrato - nuova_larghezza) // 2
    pos_y = (dimensione_quadrato - nuova_altezza) // 2
    sfondo_sfumato.paste(logo_ridimensionato, (pos_x, pos_y), logo_ridimensionato)
    
    sfondo_sfumato.save(path_salvataggio, "PNG")


def applica_fix_wikimedia(url):
    """Applica le espressioni regolari e i rimpiazzi per i link Wikimedia/Wikipedia"""
    if "upload.wikimedia.org" in url:
        if "/thumb/" in url:
            url = re.sub(r'/thumb(/.*)/[^/]+$', r'\1', url)
        if url.lower().endswith('.svg'):
            nome_svg = url.split('/')[-1]
            url = url.replace("wikipedia/commons/", "wikipedia/commons/thumb/")
            url = url.replace("wikipedia/it/", "wikipedia/it/thumb/")
            url = f"{url}/500px-{nome_svg}.png"
    return url


def elabora_m3u_e_genera_loghi():
    m3u_remote_url = "https://raw.githubusercontent.com/leanhhu061206/LIVETV/refs/heads/main/vavoo.m3u"
    output_folder = "Loghi-Quadrati"
    output_m3u = "vavoo_quadrato.m3u"
    dimensione_quadrato = 600
    url_base_github = "https://raw.githubusercontent.com/wes1993/loghi-tv/refs/heads/main/Loghi-Quadrati/"
    
    headers_standard = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    print(f"🌐 Scaricamento del file M3U remoto da: {m3u_remote_url} ...")
    try:
        response_m3u = requests.get(m3u_remote_url, headers=headers_standard, timeout=15)
        response_m3u.raise_for_status()
        lines = response_m3u.text.splitlines()
    except Exception as e:
        print(f"❌ Errore critico durante il download del file M3U: {e}")
        return

    # Inizializzazione corretta delle strutture dati
    categorie_mappate = {}
    categoria_corrente = "SENZA_CATEGORIA"
    linee_intestazione = []

    loghi_elaborati = {}  
    canali_senza_logo = []
    contatore_creati = 0

    print("⚡ Inizio scansione playlist e generazione immagini...")

    for i in range(len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        # 1. Intercettiamo l'intestazione standard dell'M3U
        if line.startswith("#EXTM3U"):
            linee_intestazione.append(line)
            continue

        # 2. Intercettiamo i commenti delle categorie (es. # RAI, # NEWS)
        if line.startswith("#") and not line.startswith("#EXTINF"):
            categoria_corrente = line.replace("#", "").strip()
            if categoria_corrente not in categorie_mappate:
                categorie_mappate[categoria_corrente] = []
            continue

        # 3. Processiamo i canali veri e propri
        if line.startswith("#EXTINF"):
            nome_canale_match = re.search(r',([^,]+)$', line)
            nome_canale = nome_canale_match.group(1).strip() if nome_canale_match else "Canale Sconosciuto"
            
            logo_match = re.search(r'tvg-logo="([^"]*)"', line)
            
            nome_canale_pulito = nome_canale.lower()
            nome_canale_pulito = re.sub(r'\s+', '-', nome_canale_pulito)
            nome_canale_pulito = re.sub(r'[^a-z0-9\-_]', '', nome_canale_pulito)
            nome_immagine_locale = f"{nome_canale_pulito}.png"
            
            path_immagine_locale = os.path.join(output_folder, nome_immagine_locale)
            url_remoto_finale = f"{url_base_github}{nome_immagine_locale}"
            
            if logo_match and logo_match.group(1).strip():
                url_logo_originale = logo_match.group(1).strip()
                url_logo_originale = applica_fix_wikimedia(url_logo_originale)
                
                if url_logo_originale in loghi_elaborati:
                    line = line.replace(logo_match.group(1).strip(), loghi_elaborati[url_logo_originale])
                else:
                    if os.path.exists(path_immagine_locale):
                        loghi_elaborati[url_logo_originale] = url_remoto_finale
                        line = line.replace(logo_match.group(1).strip(), url_remoto_finale)
                    else:
                        try:
                            scarica_e_processa_logo(url_logo_originale, path_immagine_locale, dimensione_quadrato)
                            loghi_elaborati[url_logo_originale] = url_remoto_finale
                            line = line.replace(logo_match.group(1).strip(), url_remoto_finale)
                            contatore_creati += 1
                            print(f"✅ Generato quadrato per: {nome_canale} -> {nome_immagine_locale}")
                            
                        except Exception as e:
                            print(f"⚠️ Errore nel download di {url_logo_originale}: {e}")
                            if USER_RUN:
                                print(f"\n🚨 ATTENZIONE: Download fallito per il canale '{nome_canale}'")
                                nuovo_url = input("🔗 Incolla un URL alternativo per il logo (o premi INVIO per saltare): ").strip()
                                
                                if nuovo_url:
                                    nuovo_url = applica_fix_wikimedia(nuovo_url)
                                    try:
                                        scarica_e_processa_logo(nuovo_url, path_immagine_locale, dimensione_quadrato)
                                        loghi_elaborati[url_logo_originale] = url_remoto_finale
                                        line = line.replace(logo_match.group(1).strip(), url_remoto_finale)
                                        contatore_creati += 1
                                        print(f"✅ Generato quadrato (da URL manuale) per: {nome_canale}")
                                    except Exception as e_manuale:
                                        print(f"❌ Fallito anche l'URL manuale: {e_manuale}")
                                        loghi_elaborati[url_logo_originale] = logo_match.group(1).strip()
                                        canali_senza_logo.append(nome_canale)
                                else:
                                    loghi_elaborati[url_logo_originale] = logo_match.group(1).strip()
                                    canali_senza_logo.append(nome_canale)
                            else:
                                loghi_elaborati[url_logo_originale] = logo_match.group(1).strip()
                                canali_senza_logo.append(nome_canale)
            else:
                if USER_RUN:
                    print(f"\n❓ IL CANALE '{nome_canale}' NON HA NESSUN LOGO NELL'M3U")
                    nuovo_url = input("🔗 Incolla un URL per questo logo (o premi INVIO per saltare): ").strip()
                    
                    if nuovo_url:
                        nuovo_url = applica_fix_wikimedia(nuovo_url)
                        try:
                            scarica_e_processa_logo(nuovo_url, path_immagine_locale, dimensione_quadrato)
                            contatore_creati += 1
                            print(f"✅ Generato quadrato (creato da zero) per: {nome_canale}")
                            
                            if 'tvg-logo="' in line:
                                line = re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{url_remoto_finale}"', line)
                            else:
                                line = re.sub(r'(#EXTINF:-?\d+)', rf'\1 tvg-logo="{url_remoto_finale}"', line)
                                
                        except Exception as e_manuale:
                            print(f"❌ Fallito il download dell'URL inserito: {e_manuale}")
                            canali_senza_logo.append(nome_canale)
                    else:
                        canali_senza_logo.append(nome_canale)
                else:
                    canali_senza_logo.append(nome_canale)
            
            # Recuperiamo la riga successiva che contiene il link stream del canale
            link_canale = ""
            if i + 1 < len(lines):
                link_canale = lines[i+1].strip()
                
            # Assegniamo la coppia (riga_info, link_streaming) alla categoria corretta
            if categoria_corrente not in categorie_mappate:
                categorie_mappate[categoria_corrente] = []
            categorie_mappate[categoria_corrente].append((line, link_canale))

    # --- RICOSTRUZIONE FILE ORDINATO ---
    linee_generate = list(linee_intestazione)
    
    # Richiamo alla funzione adhoc per l'ordinamento delle categorie
    categorie_pronte = ordina_categorie(categorie_mappate, ORDINE_CATEGORIE)
    
    # Generazione delle linee finali basate sul nuovo dizionario (ordinato o originale)
    for cat, canali in categorie_pronte.items():
        if cat != "SENZA_CATEGORIA":
            linee_generate.append(f"# {cat}")
        for extinf, link in canali:
            linee_generate.append(extinf)
            linee_generate.append(link)
    
    # Scrittura del file finale su disco
    with open(output_m3u, "w", encoding="utf-8") as f:
        for riga in linee_generate:
            f.write(riga + "\n")

    print("\n" + "="*60)
    print("📊 RESOCONTO PROCESSO DI ELABORAZIONE")
    print("="*60)
    print(f"🚀 Nuovi loghi quadrati creati/verificati: {contatore_creati}")
    print(f"📋 File playlist aggiornato generato: '{output_m3u}'")
    print(f"⚠️ Canali TOTALI senza alcun logo associato: {len(canali_senza_logo)}")
    print("="*60)

    if canali_senza_logo:
        print("\n🔍 ELENCO DEI CANALI PRIVI DI LOGO NELL'M3U ORIGINALE:")
        for canale in sorted(set(canali_senza_logo)):
            print(f"  - {canale}")


if __name__ == "__main__":
    try:
        from PIL import Image
    except ImportError:
        print("📦 Libreria 'Pillow' mancante. Installala eseguendo: pip install Pillow requests")
    else:
        elabora_m3u_e_genera_loghi()
