# Zeiterfassung Docker

Start lokal mit Docker:

```bash
docker compose up --build
```

Danach im Browser:

```text
http://localhost:8080
```

Für Portainer:

- Ordner auf den Server kopieren
- Stack mit der `docker-compose.yml` erstellen
- Port `8080` freigeben oder über Reverse Proxy veröffentlichen
- Daten liegen persistent im Ordner `data`
