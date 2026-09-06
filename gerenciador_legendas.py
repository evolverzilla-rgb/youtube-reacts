import os
import json
import time
import threading
import subprocess
import glob
import re
from json2srt import json_to_srt

# CORREÇÃO CRUCIAL: Nome do arquivo idêntico ao do seu app.py do GitHub
PLAYLIST_FILE = "dados_playilst.json"

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
        print(f"[Legendas] Erro ao ler arquivo da fila: {e}")
        return []

def thread_varredura_legendas():
    """Loop perpétuo em segundo plano que caça e baixa legendas pendentes"""
    print("[Legendas] Serviço de varredura em segundo plano INICIADO.")
    
    # Armazena os IDs que já processamos ou falhamos nesta sessão para evitar loops repetidos
    ids_processados_ou_falhos = set()
    
    while True:
        try:
            fila_atual = ler_fila_reprodutor()
            ids_na_fila = [video["id"] for video in fila_atual if "id" in video]
            
            # 1. LIMPEZA DE DISCO: Caça e apaga arquivos .json3 ou .srt que saíram da fila FIFO
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
                            print(f"[Legendas] Remoção concluída: Arquivo {nome_base} deletado pois saiu da fila.")
                        except Exception:
                            pass

            # 2. VARREDURA DE DOWNLOADS: Caça o primeiro vídeo da fila que ainda não tem legenda gerada
            for video in fila_atual:
                video_id = video.get("id")
                if not video_id:
                    continue
                
                arquivo_srt_esperado = f"legenda_{video_id}.srt"
                
                # Se o arquivo SRT já existe ou já falhou, pula para o próximo da fila
                if os.path.exists(arquivo_srt_esperado) or video_id in ids_processados_ou_falhos:
                    continue
                
                print(f"[Legendas] Novo vídeo detectado na fila: {video_id}. Iniciando delay de segurança de 60s...")
                
                # Pausa estratégica de 60 segundos para desarmar o anti-bot do YouTube (Erro 429)
                # time.sleep(60)
                
                # BLINDAGEM CONTRA CORTES VISUAIS DA INTEGRAÇÃO
                dominio_yt = "https://www.youtube.com"
                rota_watch = "/watch?v="
                url_completa = dominio_yt + rota_watch + video_id
                
                arquivo_saida_template = f"legenda_{video_id}.%(ext)s"
                
                # Comando com o sleep interno do yt-dlp para furar o bloqueio
                comando = [
                    "yt-dlp",
                    "--write-auto-sub",
                    "--sub-lang", "en",
                    "--sub-format", "json3",
                    "--skip-download",
                    "--ignore-no-formats-error",
                    "--extractor-args", "youtube:player_client=web",
                    "--sleep-subtitles", "60",  # <--- A INSERÇÃO CRUCIAL AQUI
                    "-o", arquivo_saida_template,
                    url_completa
                ]
                
                try:
                    print(f"[Legendas] Executando download do metadado JSON3 para {video_id}...")
                    subprocess.run(comando, capture_output=True, text=True, check=True)
                    
                    # Localiza o arquivo real gerado (o yt-dlp insere o idioma no meio do nome)
                    arquivos_json3_gerados = glob.glob(f"legenda_{video_id}*.json3")
                    
                    if arquivos_json3_gerados:
                        caminho_json3_real = arquivos_json3_gerados[0]
                        print(f"[Legendas] Download concluído! Chamando o módulo global json2srt para converter...")
                        
                        # Executa a sua sub-rotina do json2srt.py enviando o arquivo baixado
                        json_to_srt(caminho_json3_real, arquivo_srt_esperado)
                        
                        # Remove apenas o JSON3 intermediário para deixar a pasta limpa
                        if os.path.exists(caminho_json3_real):
                            os.remove(caminho_json3_real)
                            
                        print(f"[Legendas] Sucesso! Vídeo {video_id} está com a legenda pronta em disco.")
                    else:
                        print(f"[Legendas] Erro: O arquivo JSON3 não foi gerado para o vídeo {video_id}.")
                        ids_processados_ou_falhos.add(video_id)
                        
                except subprocess.CalledProcessError as err_sub:
                    print(f"[Legendas] Falha na requisição externa do yt-dlp para {video_id}: {err_sub.stderr}")
                    ids_processados_ou_falhos.add(video_id)
                except Exception as e:
                    print(f"[Legendas] Erro inesperado ao processar {video_id}: {e}")
                    ids_processados_ou_falhos.add(video_id)
                
                # Para o loop interno da fila para voltar ao topo e ler o arquivo JSON atualizado
                break
                
        except Exception as e:
            print(f"[Legendas] Erro crítico no loop da thread: {e}")
            
        time.sleep(5)

def iniciar_servico_legendas():
    """Inicia a sub-rotina global de legendas em uma Thread separada"""
    threading_worker = threading.Thread(target=thread_varredura_legendas, daemon=True)
    threading_worker.start()
