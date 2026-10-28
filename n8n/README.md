# Fluxo no n8n (etapa 3)

Um workflow por canal (ou um só, com um Schedule Trigger por canal):

1. **Schedule Trigger** com o cron do canal.
2. **HTTP Request** `POST http://worker:8787/runs` com `{"channel": "<slug>"}` e o cabeçalho
   `Authorization: Bearer {{$env.FABRICA_API_TOKEN}}`. Guarda o `video_id`.
3. **Wait** 10 minutos, depois **HTTP Request** `GET /runs/{{video_id}}`.
4. **IF** `status` é `running` ou `queued`: volta para o passo 3 (limite de 12 voltas).
5. **IF** `status` é `failed`: Telegram com o erro e um botão para `POST /runs/{id}/resume`.
6. **IF** `status` é `scheduled`: Telegram com título, link e horário.

O pipeline já agenda a publicação 30 minutos depois do fim do vídeo; o n8n só dispara e acompanha.
