import os
import json
import time
import threading
import subprocess
import glob
import re
from json2srt import json_to_srt

# Mantendo o mesmo nome exato do arquivo do seu repositório
PLAYLIST_FILE = "dados_playlist.json"
LOG_FILE = "legendas.log"

def gravar_no_log(mensagem):
    """Escreve as mensagens de monitoramento no arquivo de log isolado com timestamp"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    linha_log = f"[{timestamp}] {mensagem}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha_log)
    except Exception as e:
        print(f"Erro ao gravar no arquivo de log: {e}")

def ler_fila_reprodutor():
    """Lê a fila FIFO diretamente do arquivo JSON com segurança"""
    if not os.path.exists(PLAYLIST_FILE):
        return []
    try:
        with open(PLAYLIST_FILE, 'r', encoding='utf-8') as f:
            conteudo = f.read().strip()
            if not conteudo:
                return []
            return json.loads(conteudo)
    except Exception as e:
        gravar_no_log(f"Erro ao ler arquivo da fila: {e}")
        return []

def thread_varredura_legendas():
    """Loop perpétuo em segundo plano que caça e baixa legendas pendentes de forma silenciosa"""
    gravar_no_log("Serviço de varredura em segundo plano INICIADO com sucesso.")
    
    # Armazena os IDs que já processamos ou falhamos nesta sessão para evitar loops repetidos
    ids_processados_ou_falhos = set()
    
    while True:
        try:
            fila_atual = ler_fila_reprodutor()
            ids_na_fila = [video["id"] for video in fila_atual if "id" in video]
            
            # 1. LIMPEZA DE DISCO: Caça e apaga arquivos locais que já saíram da fila FIFO
            arquivos_srt_locais = glob.glob("legenda_*.srt")
            arquivos_json3_locais = glob.glob("legenda_*.json3")
            todos_arquivos_locais = arquivos_srt_locais + arquivos_json3_locais
            
            for arq in todos_arquivos_locais:
                nome_base = os.path.basename(arq)
                match = re.match(r"legenda_([a-zA-Z0-9_-]{11})", nome_base)
                if match:
                    id_extraido = match.group(1)
                    if id_extraido not in ids_na_fila:
                        try:
                            os.remove(arq)
                            gravar_no_log(f"Remoção concluída: Arquivo {nome_base} deletado pois saiu da fila FIFO.")
                        except Exception:
                            pass

            # 2. VARREDURA DE DOWNLOADS: Analisa a fila elemento por elemento
            for video in fila_atual:
                video_id = video.get("id")
                if not video_id:
                    continue
                
                arquivo_srt_esperado = f"legenda_{video_id}.srt"
                
                # Se a legenda já existe localmente, pula para o próximo vídeo
                if os.path.exists(arquivo_srt_esperado):
                    continue
                    
                # CORREÇÃO CRUCIAL AQUI: Se o vídeo já falhou antes, expurga ele do JSON agora mesmo!
                if video_id in ids_processados_ou_falhos:
                    gravar_no_log(f"⚠️ Alerta: O vídeo <{video_id}> está na lista de falhas/membros. Removendo automaticamente da fila...")
                    try:
                        fila_reaberta = ler_fila_reprodutor()
                        nova_fila = [v for v in fila_reaberta if v.get("id") != video_id]
                        
                        with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f_salvar:
                            json.dump(nova_fila, f_salvar, indent=4, ensure_ascii=False)
                            
                        gravar_no_log(f"✅ Sucesso: Vídeo problemático <{video_id}> expurgado da lista.")
                    except Exception as erro_json:
                        gravar_no_log(f"Erro ao tentar remover o vídeo do JSON: {erro_json}")
                    continue
                
                gravar_no_log(f"Legenda não existe para o vídeo <{video_id}>, iniciando os preparativos para baixar.")
                
                dominio_yt = "https://youtube.com"
                rota_watch = "/watch?v="
                url_completa = dominio_yt + rota_watch + video_id
                
                arquivo_saida_template = f"legenda_{video_id}.json3"
                
                comando = [
                    "yt-dlp",
                    "--write-auto-sub",
                    "--sub-lang", "pt",  
                    "--sub-format", "json3",
                    "--skip-download",
                    "--ignore-no-formats-error",
                    "--sleep-subtitles", "60",
                    "-o", arquivo_saida_template,
                    url_completa
                ]
                
                string_comando_visual = " ".join(comando)
                gravar_no_log(f"Invocando o terminal. Comando executado: {string_comando_visual}")
                
                try:
                    gravar_no_log(f"Executando download do metadado JSON3 para {video_id}...")
                    
                    with open(LOG_FILE, "a", encoding="utf-8") as f_log:
                        subprocess.run(comando, stdout=f_log, stderr=f_log, text=True, check=True)
                    
                    arquivos_json3_gerados = glob.glob(f"legenda_{video_id}*.json3")
                    
                    if arquivos_json3_gerados:
                        caminho_json3_real = arquivos_json3_gerados[0]
                        gravar_no_log(f"Download concluído com sucesso! Chamando o módulo global json2srt para converter...")
                        
                        json_to_srt(caminho_json3_real, arquivo_srt_esperado)
                        
                        if os.path.exists(caminho_json3_real):
                            os.remove(caminho_json3_real)
                            
                        gravar_no_log(f"Sucesso! Vídeo {video_id} está com a legenda em português pronta em disco.")
                    else:
                        gravar_no_log(f"Erro: O arquivo JSON3 não foi encontrado na pasta para o vídeo {video_id} pós-download.")
                        ids_processados_ou_falhos.add(video_id)
                        
                except subprocess.CalledProcessError as err_sub:
                    erro_texto = ""
                    if os.path.exists(LOG_FILE):
                        try:
                            with open(LOG_FILE, "r", encoding="utf-8") as f_leitura_erro:
                                erro_texto = "".join(f_leitura_erro.readlines()[-20:])
                        except Exception:
                            pass

                    if "Members-only" in erro_texto or "Join this channel" in erro_texto or "Private video" in erro_texto or "removed by the uploader" in erro_texto.lower() or "403" in erro_texto:
                        gravar_no_log(f"⚠️ Alerta: O vídeo <{video_id}> mudou para APENAS MEMBROS ou PRIVADO. Removendo automaticamente da lista...")
                        try:
                            fila_reaberta = ler_fila_reprodutor()
                            nova_fila = [v for v in fila_reaberta if v.get("id") != video_id]
                            
                            with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f_salvar:
                                json.dump(nova_fila, f_salvar, indent=4, ensure_ascii=False)
                                
                            gravar_no_log(f"✅ Sucesso: Vídeo <{video_id}> expurgado do arquivo dados_playlist.json.")
                        except Exception as erro_json:
                            gravar_no_log(f"Erro ao tentar remover o vídeo do JSON: {erro_json}")
                    else:
                        gravar_no_log(f"Falha na requisição externa do yt-dlp para {video_id}. Veja o erro completo no legendas.log")
                        ids_processados_ou_falhos.add(video_id)
                        
                except Exception as e:
                    gravar_no_log(f"Erro inesperado ao processar {video_id}: {e}")
                    ids_processados_ou_falhos.add(video_id)
                
                break
                
        except Exception as e:
            gravar_no_log(f"Erro crítico no loop da thread: {e}")
            
        time.sleep(5)

def iniciar_servico_legendas():
    """Inicia a sub-rotina global de legendas em uma Thread separada"""
    threading_worker = threading.Thread(target=thread_varredura_legendas, daemon=True)
    threading_worker.start()
