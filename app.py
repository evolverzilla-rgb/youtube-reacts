import re
import os
import json
import yt_dlp
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
DATA_FILE = "dados_playlist.json"

# Deixamos o estado inicial vazio para que o Python force a leitura do disco na primeira checagem
# Adicione os campos "cc" e "lang" na sua variável original:
estado_global = {
    "video_atual_id": None,
    "status": "pausado",
    "tempo_atual": 0,
    "velocidade": 1.0,
    "cc": 0,         # <--- 0 = Desativado, 1 = Ativado
    "lang": "pt"     # <--- Idioma padrão (ex: pt, en, es)
}

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

def ler_playlist():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def salvar_playlist(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

@app.route('/')
def index_dock(): return render_template('dock.html')

@app.route('/player')
def index_player(): return render_template('player_obs.html')

@app.route('/monitor')
def index_monitor(): return render_template('monitor.html')

# Certifique-se de que a sua variável estado_global no topo do arquivo tenha a velocidade padrão inicializada:
# estado_global = {"video_atual_id": None, "status": "pausado", "tempo_atual": 0, "velocidade": 1.0}

@app.route('/api/estado_sincronizado', methods=['GET'])
def get_estado_sincronizado():
    global estado_global
    playlist = ler_playlist()
    
    # Captura a velocidade
    nova_velocidade = request.args.get('velocidade')
    if nova_velocidade:
        try: estado_global["velocidade"] = float(nova_velocidade)
        except ValueError: pass
            
    # CAPTURA DE LEGENDA: Monitor avisa se ativou CC ou mudou idioma
    novo_cc = request.args.get('cc')
    if novo_cc is not None:
        estado_global["cc"] = int(novo_cc)
        
    novo_lang = request.args.get('lang')
    if novo_lang:
        estado_global["lang"] = novo_lang
            
    if playlist and len(playlist) > 0:
        topo = playlist[0]
        if estado_global["video_atual_id"] is None or estado_global["video_atual_id"] != topo["id"]:
            estado_global["video_atual_id"] = topo["id"]
            estado_global["status"] = "tocando"
            estado_global["tempo_atual"] = 0
    else:
        estado_global["video_atual_id"] = None
        estado_global["status"] = "pausado"
        estado_global["tempo_atual"] = 0
        
    # INSERÇÃO: Varre os itens da lista e injeta o status de download da legenda
    for video in playlist:
        v_id = video.get("id")
        if v_id:
            if os.path.exists(f"legenda_{v_id}.srt"):
                video["status_legenda"] = "Pronto"
            else:
                video["status_legenda"] = "Baixando Legendas"
        
    return jsonify({
        "id": estado_global["video_atual_id"],
        "status": estado_global["status"],
        "tempo": estado_global["tempo_atual"],
        "velocidade": estado_global.get("velocidade", 1.0),
        "cc": estado_global.get("cc", 0),       
        "lang": estado_global.get("lang", "pt"), 
        "lista_completa": playlist  # <--- Enviado com os novos selos
    })

@app.route('/api/log_erros_legendas')
def api_log_erros_legendas():
    LOG_FILE = "legendas.log"
    erros = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                linhas = f.readlines()
                for linha in linhas:
                    if "⚠️ Alerta" in linha or "expurgado" in linha:
                        erros.append(linha.strip())
        except Exception:
            pass
    return jsonify(erros[-10:])

@app.route('/api/adicionar', methods=['POST'])
def adicionar():
    dados = request.json
    url = dados.get('url')
    ouvinte = dados.get('ouvinte', 'Anônimo')
    
    ydl_opts = {'quiet': True, 'skip_download': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            titulo, video_id = info.get('title', 'Vídeo sem título'), info.get('id')
    except Exception:
        return jsonify({"erro": "URL inválida"}), 400
        
    playlist = ler_playlist()
    novo_item = {
        "id": video_id,
        "titulo": titulo,
        "ouvinte": ouvinte,
        "status": "tocando"
    }
    playlist.append(novo_item)
    salvar_playlist(playlist)
    return jsonify(playlist)

@app.route('/api/remover/<video_id>', methods=['DELETE'])
def remover(video_id):
    global estado_global
    playlist = ler_playlist()
    playlist = [item for item in playlist if item['id'] != video_id]
    salvar_playlist(playlist)
    
    if estado_global["video_atual_id"] == video_id:
        estado_global["video_atual_id"] = None
        estado_global["status"] = "pausado"
        estado_global["tempo_atual"] = 0
        
    return jsonify(playlist)

@app.route('/api/mover_para_proximo/<video_id>', methods=['POST'])
def mover_para_proximo(video_id):
    playlist = ler_playlist()
    if len(playlist) <= 2: return jsonify(playlist)
    item_para_mover = next((item for item in playlist if item['id'] == video_id), None)
    if item_para_mover:
        playlist.remove(item_para_mover)
        playlist.insert(1, item_para_mover)
        salvar_playlist(playlist)
    return jsonify(playlist)

@app.route('/api/status', methods=['POST'])
def alterar_status():
    global estado_global
    dados = request.json
    status = dados.get('status')
    
    playlist = ler_playlist()
    if playlist and len(playlist) > 0:
        playlist[0]['status'] = status
        salvar_playlist(playlist)
        
    estado_global["status"] = status
    return jsonify(estado_global)

@app.route('/api/atualizar_tempo', methods=['POST'])
def atualizar_tempo():
    global estado_global
    dados = request.json
    estado_global["tempo_atual"] = dados.get('tempo', 0)
    return jsonify({"sucesso": True})

@app.route('/api/toggle', methods=['GET'])
def streamdeck_toggle():
    global estado_global
    playlist = ler_playlist()
    if playlist and len(playlist) > 0:
        if estado_global["status"] == 'tocando':
            estado_global["status"] = 'pausado'
            playlist[0]['status'] = 'pausado'
        else:
            estado_global["status"] = 'tocando'
            playlist[0]['status'] = 'tocando'
        salvar_playlist(playlist)
    return jsonify({"status": estado_global["status"]})

# --- ROTA DE EXTRAÇÃO DE SRT PARA O OBS CORRIGIDA ---
@app.route('/api/legendas_sincronizadas')
def api_legendas_sincronizadas():
    video_id = request.args.get('id')
    if not video_id:
        return jsonify([])
        
    arquivo_srt = f"legenda_{video_id}.srt"
    linhas_legendas = []
    
    if os.path.exists(arquivo_srt):
        try:
            with open(arquivo_srt, "r", encoding="utf-8") as f:
                conteudo = f.read()
                blocos = conteudo.strip().split('\n\n')
                
                for bloco in blocos:
                    partes_bloco = bloco.split('\n')
                    if len(partes_bloco) >= 3:
                        # Identifica a linha do tempo (segunda linha do bloco SRT)
                        linha_tempo = partes_bloco[1]
                        tempos = linha_tempo.split(' --> ')
                        
                        if len(tempos) == 2:
                            # Função interna estável para converter HH:MM:SS,mmm para segundos
                            def srt_para_segundos(t_str):
                                try:
                                    t_str = t_str.replace(',', '.').strip()
                                    p = t_str.split(':')
                                    h = float(p[0])
                                    m = float(p[1])
                                    s = float(p[2])
                                    return (h * 3600) + (m * 60) + s
                                except Exception:
                                    return 0.0
                                
                            tempo_inicio = srt_para_segundos(tempos[0])
                            tempo_fim = srt_para_segundos(tempos[1])
                            
                            # Une o texto (linhas 3 em diante)
                            texto_linha = " ".join(partes_bloco[2:]).strip()
                            texto_linha = re.sub(r'<[^>]*>', '', texto_linha)
                            texto_linha = re.sub(r'\s+', ' ', texto_linha)
                            
                            if texto_linha:
                                linhas_legendas.append({
                                    "inicio": tempo_inicio,
                                    "fim": tempo_fim,
                                    "texto": texto_linha
                                })
        except Exception as err:
            print(f"Erro ao processar arquivo SRT {arquivo_srt}: {err}")
            
    return jsonify(linhas_legendas)


# --- INSERÇÃO DA SUB-ROTINA DO GERENCIADOR DE LEGENDAS ---
from gerenciador_legendas import iniciar_servico_legendas
iniciar_servico_legendas()
# ---------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)
