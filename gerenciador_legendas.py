def thread_varredura_legendas():
    """Loop perpétuo em segundo plano que caça e baixa legendas pendentes de forma silenciosa"""
    gravar_no_log("Serviço de varredura em segundo plano INICIADO com sucesso.")
    
    # Armazena os IDs que já processamos ou falhamos nesta sessão para evitar loops repetidos
    ids_processados_ou_falhos = set()
    
    # AUDITORIA INICIAL: Verifica se o arquivo da playlist existe no disco antes do loop
    if os.path.exists(PLAYLIST_FILE):
        gravar_no_log(f"Auditoria: O arquivo [{PLAYLIST_FILE}] foi localizado com sucesso no disco.")
    else:
        gravar_no_log(f"Auditoria AVISO: O arquivo [{PLAYLIST_FILE}] NÃO existe na pasta atual. Um novo será monitorado.")

    while True:
        try:
            # SINALIZAÇÃO DE ENTRADA NO LOOP: Para termos certeza que o While disparou
            gravar_no_log("--- Nova varredura cíclica da fila iniciada ---")
            
            fila_atual = ler_fila_reprodutor()
            ids_na_fila = [video["id"] for video in fila_atual if "id" in video]
            
            gravar_no_log(f"Varredura: Fila lida com sucesso. Total de vídeos encontrados: {len(ids_na_fila)}")

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
                
                # SINALIZAÇÃO 1: Legenda já existe localmente ou está marcada como falha (Vídeo Pulado)
                if os.path.exists(arquivo_srt_esperado):
                    gravar_no_log(f"Legenda existe, o vídeo <{video_id}> foi pulado.")
                    continue
                    
                if video_id in ids_processados_ou_falhos:
                    gravar_no_log(f"O vídeo <{video_id}> já falhou anteriormente nesta sessão, pulando para evitar travamento.")
                    continue
                
                # SINALIZAÇÃO 2: Legenda não encontrada (Vídeo entra em modo download)
                gravar_no_log(f"Legenda não existe para o vídeo <{video_id}>, iniciando os preparativos para baixar.")
                
                dominio_yt = "https://youtube.com"
                rota_watch = "/watch?v="
                url_completa = dominio_yt + rota_watch + video_id
                
                arquivo_saida_template = f"legenda_{video_id}.%(ext)s"
                
                comando = [
                    "yt-dlp",
                    "--write-auto-sub",
                    "--sub-lang", "pt.*",  
                    "--sub-format", "json3",
                    "--skip-download",
                    "--ignore-no-formats-error",
                    "--extractor-args", "youtube:player_client=web",
                    "--sleep-subtitles", "60",
                    "-o", arquivo_saida_template,
                    url_completa
                ]
                
                # SINALIZAÇÃO 3: Imprime a linha de comando exata antes de invocar o Subprocess
                string_comando_visual = " ".join(comando)
                gravar_no_log(f"Invocando o terminal. Comando executado: {string_comando_visual}")
                
                try:
                    gravar_no_log(f"Executando download do metadado JSON3 para {video_id}...")
                    
                    with open(LOG_FILE, "a", encoding="utf-8") as f_log:
                        subprocess.run(comando, stdout=f_log, stderr=f_log, text=True, check=True)
                    
                    # Localiza o arquivo real gerado na pasta
                    arquivos_json3_gerados = glob.glob(f"legenda_{video_id}*.json3")
                    
                    if arquivos_json3_gerados:
                        caminho_json3_real = arquivos_json3_gerados[0]
                        gravar_no_log(f"Download concluído com sucesso! Chamando o módulo global json2srt para converter...")
                        
                        # Executa a sua sub-rotina enviando o caminho em texto puro
                        json_to_srt(caminho_json3_real, arquivo_srt_esperado)
                        
                        # Remove apenas o JSON3 intermediário para deixar a pasta limpa
                        if os.path.exists(caminho_json3_real):
                            os.remove(caminho_json3_real)
                            
                        gravar_no_log(f"Sucesso! Vídeo {video_id} está com a legenda em português pronta em disco.")
                    else:
                        gravar_no_log(f"Erro: O arquivo JSON3 não foi encontrado na pasta para o vídeo {video_id} pós-download.")
                        ids_processados_ou_falhos.add(video_id)
                        
                except subprocess.CalledProcessError as err_sub:
                    gravar_no_log(f"Falha na requisição externa do yt-dlp para {video_id}. Verifique as linhas de log do yt-dlp acima.")
                    ids_processados_ou_falhos.add(video_id)
                except Exception as e:
                    gravar_no_log(f"Erro inesperado ao processar {video_id}: {e}")
                    ids_processados_ou_falhos.add(video_id)
                
                # Quebra a fila para voltar ao topo e reavaliar o arquivo JSON
                break
                
        except Exception as e:
            gravar_no_log(f"Erro crítico no loop da thread: {e}")
            
        # Tempo de folga cíclica do loop
        time.sleep(5)
