# Plano: adicionar áudio (música de fundo) aos vídeos

## Objetivo
Embed de uma trilha de fundo (Pixabay Music) no `.mp4` final gerado pelo projeto, mantendo o pipeline atual intacto. Voz/SFX fora de escopo.

---

## Decisões fechadas

| # | Decisão |
|---|---------|
| 1 | Tipo: só música de fundo (sem voz, sem SFX) |
| 2 | Fonte: Pixabay Music API |
| 3 | Mapping tema→trilha: novo campo `musica_busca` em cada tema de `temas.py` |
| 4 | UI picker: só no `server.py` (auto flow + manual flow) |
| 5 | CLI `gerar.py`: **sem áudio** (decisão explícita do usuário) |
| 6 | Auto `auto_gerar.py`: auto-pick aleatório do top 5 |
| 7 | Saída: single `.mp4` com áudio embed |
| 8 | Length mismatch: **loop** se trilha menor · **fade-out 0.8s + cut** se maior |
| 9 | Volume / fade-in: **50%** / **0.4s** (configurável via `opcoes`) |
| 10 | Cache: **nenhum** — cada geração re-baixa (decisão do usuário, com aviso) |
| 11 | Pipeline: modifica `nucleo.montar_video()` (single ffmpeg pass) |
| 12 | Módulo novo: `pixabay_audio.py` + chave `pixabay_key=...` em `segredos.txt` |
| 13 | Preview: temp dir por sessão + HTTP Range |
| 14 | Picker UI: aparece em `_preparar_auto` + seção extra em modo manual |
| 15 | Exibição: mostra duração formatada (ex: `"2:34"`) em cada card |
| 16 | Refetch: descarta seleção atual; `audio_id` viaja no body do `/api/gerar`; server re-fallback se id sumiu |
| 17 | Falha Pixabay: **soft fail** — vídeo sai sem áudio + log de aviso (nunca bloqueia geração) |

---

## Arquivos a criar / modificar

### 1. `pixabay_audio.py` (NOVO)
Mesmo padrão de `pexels.py`:
- `BASE_DIR` / `SEGREDOS` pointing to `segredos.txt`
- `ler_chave_pixabay()` → lê `pixabay_key=...`
- `buscar_opcoes(query, n=5, chave=None)` → lista de dicts:
  ```
  { "id": int, "title": str, "duration": int, "duration_str": "M:SS",
    "url_download": str, "tags": [str] }
  ```
- `baixar_track(url, destino)` → baixa MP3 em bytes via urllib
- `User-Agent` igual ao de `pexels.py`

Endpoint Pixabay a usar:
```
GET https://pixabay.com/api/?key=<KEY>&q=<QUERY>&per_page=5&category=music
```
(Ou o endpoint específico de audio, conforme docs.)

### 2. `segredos.txt`
Acrescentar linha:
```
pixabay_key=<chave do usuário>
```

### 3. `temas.py`
Para cada um dos 18 temas, adicionar campo `musica_busca` com keyword em inglês adequada ao estilo "ambient/hopeful/cinematic/inspirational". Fallback chain no consumidor:
1. `tema["musica_busca"]`
2. `tema["busca"]`
3. `"ambient hopeful inspirational background"`

### 4. `nucleo.py` — estender `montar_video()`
Adicionar campos opcionais em `opcoes`:
- `audio_path` (caminho de MP3 no disco) — `None` desabilita
- `volume_audio` (default `0.5`)
- `fade_in_audio` (default `0.4`)
- `fade_out_audio` (default `0.8`)

Lógica ffmpeg:
- Quando `audio_path` é fornecido: adicionar `-i <audio_path>` aos inputs
- Aplicar filter chain no audio:
  - Se trilha menor que o vídeo: `aloop=loop=-1:size=1e9,atrim=duration=<video_dur>`
  - Se trilha maior: `atrim=duration=<video_dur>`
  - Sempre: `volume=<v>,afade=in:st=0:d=<fade_in>,afade=out:st=<video_dur-fade_out>:d=<fade_out>`
- Mapear ambos os streams: `-map [v_out] -map [a_out]`
- `-c:a aac -b:a 128k` para o audio stream
- Manter `-c:v libx264 -pix_fmt yuv420p` sem re-encode do vídeo

### 5. `auto_gerar.py` — adicionar fluxo de áudio
Após passo 3 (Pexels imagens), inserir passo "3b":
```
busca_audio = tema_obj.get("musica_busca") or tema_obj["busca"]
opcoes_audio = pixabay_audio.buscar_opcoes(busca_audio, n=5)
if opcoes_audio:
    pick = random.choice(opcoes_audio)
    audio_path = tempfile.mktemp(suffix=".mp3")
    pixabay_audio.baixar_track(pick["url_download"], audio_path)
    opcoes["audio_path"] = audio_path
else:
    _stderr("       ! sem audio (Pixabay music vazio)")
```

Adicionar `random` ao import (já tem? checar) e `import pixabay_audio`.

### 6. `server.py` — endpoints novos + modificações

**Novos endpoints:**
- `GET /api/audio/buscar?tema=X` ou `?query=X` → JSON `{ "opcoes": [{id, title, duration, duration_str, preview_url}, ...] }`
- `GET /api/audio/preview/<track_id>` → serve MP3 do temp dir com Range support

**Modificações:**
- `_preparar_auto`: incluir `audio_opcoes` na resposta (busca + 5 opções)
- `_gerar`: aceitar `audio_id` no body; se presente, baixa track e passa em `opcoes["audio_path"]`; se id não está nas opções correntes, fallback aleatório
- Servir `/api/audio/file/<track_id>` (Range) para os previews
- Limpar temp dir de áudio no shutdown (`atexit` ou `try/finally` no `main()`)

**Lifecycle do temp dir:**
- Criar sob demanda: `tempfile.mkdtemp(prefix="audio_sess_")`
- Mapeamento `track_id → path` em dict em memória
- GC no shutdown

### 7. `web/index.html` + `web/app.js` + `web/estilo.css` — UI do picker

**No painel "Auto: tema → vídeo":**
Bloco após o textarea de frases:
```html
<div class="audio-picker" id="audioAuto">
  <h3>Música</h3>
  <div class="audio-opcoes" id="audioOpcoesAuto">
    <!-- 5 cards injetados via JS -->
  </div>
  <button id="audioRefetchAuto">Buscar outras 5</button>
  <input type="hidden" id="audioIdAuto" />
</div>
```

**No painel manual** (modo "Upload + textos"):
Seção análoga com `<div class="audio-picker" id="audioManual">`.

**Cada card de áudio:**
```html
<div class="audio-card" data-id="...">
  <span class="audio-title">Soft Piano Ambient</span>
  <span class="audio-duration">2:34</span>
  <audio controls preload="none" src="/api/audio/preview/12345"></audio>
  <button class="audio-pick">Escolher</button>
</div>
```

**JS logic:**
- `buscarOpcoes(query)` → `GET /api/audio/buscar?query=X`
- Render dos cards
- Click em "Escolher" → marca selecionado, grava id no hidden input
- Click em "Buscar outras 5" → refaz a busca, descarta seleção
- Click em play no `<audio>` → preview 10s (browser toca do começo até pausar)

**CSS:**
- Grid responsivo de cards (1 coluna mobile, 2-3 desktop)
- Estado selecionado: borda destacada
- Layout do player de áudio compacto

---

## Verificação (smoke test)

1. **Sem chave Pixabay**: gerar via `auto_gerar.py` → vídeo sai sem áudio, stderr mostra warning.
2. **Com chave, caminho auto**: rodar `auto_gerar.py lei_da_atracao` → ffprobe mostra 2 streams (video+audio), volume audível, sem cortes abruptos.
3. **Com chave, UI manual**: abrir `server.py`, fluxo manual, escolher uma faixa, gerar → idem.
4. **Refetch**: clicar "Buscar outras 5" → 5 novos cards, seleção anterior descartada.
5. **Audio id stale**: gerar com `audio_id` que não está entre as 5 atuais → server re-faz fallback aleatório.
6. **Length mismatch**: testar com trilha < vídeo (loop perceptível OK) e > vídeo (fade-out + corte).
7. **`gerar.py` CLI**: continua gerando vídeo sem áudio.

---

## Riscos / observações

- **Sem cache** (decisão do usuário): em batch pode bater rate-limit do Pixabay (~100 req/min na free tier). Cada `auto_gerar` faz: 1× busca de 5 + 1× download da escolhida = 2 req.
- **Pixabay Music endpoint**: confirmar URL exata e campo `category` (pode ser `music` ou outro). Verificar docs se categoria ou tag funciona.
- **ffmpeg loop filter**: usar `aloop=loop=-1:size=1e9` antes do `atrim` para trilhas curtas.
- **HTTP Range**: implementar `do_GET` em `/api/audio/preview/<id>` checando `Range` header; responder 206 Partial Content quando presente.
