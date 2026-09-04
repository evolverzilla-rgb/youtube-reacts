import json
import sys
from datetime import timedelta

def format_time(ms):
    """Converte milissegundos para o formato de tempo SRT (HH:MM:SS,mmm)"""
    td = timedelta(milliseconds=ms)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    milliseconds = int(round((td.total_seconds() - total_seconds) * 1000))
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def json_to_srt(json_file_path, srt_file_path):
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    events = data.get('events', [])
    valid_events = []
    
    # 1. Primeiro, filtramos apenas os eventos que realmente contêm texto
    for event in events:
        if 'segs' not in event:
            continue
        text_parts = [seg.get('utf8', '') for seg in event['segs']]
        text = ''.join(text_parts).strip()
        if text:
            valid_events.append({
                'start_ms': event.get('tStartMs', 0),
                'duration_ms': event.get('dDurationMs', 0),
                'text': text
            })
            
    srt_lines = []
    sequence_number = 1
    total_events = len(valid_events)
    
    # 2. Agora calculamos o tempo final corrigido com base no próximo evento
    for i, current_event in enumerate(valid_events):
        start_ms = current_event['start_ms']
        
        # LÓGICA DO 4K DOWNLOADER:
        # Se houver uma próxima legenda, o fim desta será o início da próxima.
        # Caso contrário (se for a última), usamos a duração original do JSON.
        if i < total_events - 1:
            next_start_ms = valid_events[i + 1]['start_ms']
            end_ms = next_start_ms
        else:
            end_ms = start_ms + current_event['duration_ms']
        
        # Formata os tempos
        start_srt = format_time(start_ms)
        end_srt = format_time(end_ms)
        
        # Monta o bloco SRT
        srt_lines.append(f"{sequence_number}")
        srt_lines.append(f"{start_srt} --> {end_srt}")
        srt_lines.append(f"{current_event['text']}\n")
        
        sequence_number += 1
        
    # Grava o arquivo SRT final
    with open(srt_file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_lines))
    print(f"Sucesso! Arquivo convertido (estilo 4K Downloader) salvo em: {srt_file_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso correto: python converter.py <arquivo_origem.json> <arquivo_destino.srt>")
        sys.exit(1)
        
    input_json = sys.argv[1]
    output_srt = sys.argv[2]
    
    try:
        json_to_srt(input_json, output_srt)
    except Exception as e:
        print(f"Erro ao converter o arquivo: {e}")
