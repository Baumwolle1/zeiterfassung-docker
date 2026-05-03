# Zeiterfassung Docker

Eine schlanke, mobile Zeiterfassung fuer Schichtarbeit, gebaut fuer Docker, Portainer und den dauerhaften Betrieb auf einem NAS oder kleinen Server.

Die App ist darauf ausgelegt, Arbeitszeiten schnell am Handy einzutragen, Wochen und Monate sauber zu kontrollieren und am Ende einen fertigen Stundenzettel als PDF auszugeben.

## Funktionen

- Mobile Web-App fuer Handy, Tablet und Desktop
- Tagesansicht mit Schichtauswahl, Arbeitsbeginn, Arbeitsende und Notizfeld
- Wochenansicht und Monatsansicht mit schnellen Wechseln zwischen KW und Monat
- Fruehschicht, Spaetschicht, Freitag, Notdienst, Urlaub, Krank, Arztkrank, Feiertag und Frei
- Automatische Standardzeiten fuer Fruehschicht, Spaetschicht und Freitag
- Automatischer Pausenabzug bei Fruehschicht
- Spaetschicht startet standardmaessig um 11:55 Uhr und zaehlt die 5 Minuten Mehrarbeit mit
- Freitag wird immer als kurzer Arbeitstag behandelt
- Notdienst mit mehreren Zeitbloecken pro Tag
- Wochenend-Notdienst bleibt sichtbar, wird aber nicht in die normalen Wochen- und Monatsueberstunden eingerechnet
- Arztkrank kann mit Zeiten dokumentiert werden, ohne Arbeitszeit, Plusstunden oder Minusstunden zu beeinflussen
- Monatsuebersicht mit Monats-Iststunden und Monatsueberstunden
- PDF-Export direkt in die hinterlegte Stundenzettel-Vorlage fuer Elisabeth
- Docker-Setup mit persistentem `data`-Ordner

## PDF-Export

Der PDF-Export fuellt den Stundenzettel automatisch aus:

- Name und Monat werden oben eingetragen
- Fruehschicht landet im Bereich `Anwesenheit Vormittag`
- Spaetschicht landet im Bereich `Anwesenheit Nachmittag`
- Notdienst kann Vormittag und Nachmittag getrennt darstellen
- Weitere Notdienst-Zeiten werden in `Bemerkungen` notiert
- Sondertage wie Urlaub, Krank, Arztkrank und Feiertag erscheinen in `Bemerkungen`
- Im Feld `Gesamt` steht die Kernarbeitszeit des Tages
- Bei Abweichungen steht dahinter der Saldo, zum Beispiel `07:45 = +00:05`
- Unten werden Monats-Saldo, Vormonat und aktueller Stand zusammengefasst

## Schichtlogik

| Typ | Standardzeit | Wertung |
| --- | --- | --- |
| Fruehschicht | 06:45 - 15:00 | 7:45 Stunden, 30 Minuten Pause automatisch abgezogen |
| Spaetschicht | 11:55 - 19:00 | 7:00 Stunden Soll plus 5 Minuten Mehrarbeit |
| Freitag | 06:45 - 13:00 | kurzer Freitag ohne Pause |
| Notdienst | frei eintragbar | zaehlt als Stunden, Wochenend-Notdienst nicht in Gesamtueberstunden |
| Urlaub | keine Zeit | keine Istzeit, kein Saldo |
| Krank | keine Zeit | keine Istzeit, kein Saldo |
| Arztkrank | Zeit optional | nur Dokumentation, keine Wertung |
| Feiertag | keine Zeit | keine Istzeit, kein Saldo |
| Frei | keine Zeit | keine Istzeit, kein Saldo |

## Start mit Docker

```bash
docker compose up --build
```

Danach ist die App erreichbar unter:

```text
http://localhost:8091
```

Im Container laeuft die App auf Port `8080`; die mitgelieferte `docker-compose.yml` veroeffentlicht sie lokal auf Port `8091`.

## Portainer / NAS

1. Repository oder Projektordner auf den Server legen.
2. In Portainer einen neuen Stack anlegen.
3. Inhalt der `docker-compose.yml` verwenden.
4. Stack deployen.
5. App ueber Port `8091` oder ueber einen Reverse Proxy oeffnen.

Die Datenbank liegt persistent im Ordner:

```text
data/zeiterfassung.db
```

Durch das Docker-Volume `./data:/app/data` bleibt die Datenbank auch nach Container-Neustarts erhalten.

## Konfiguration

Die wichtigsten Umgebungsvariablen:

| Variable | Beschreibung |
| --- | --- |
| `APP_PASSWORD` | Passwort fuer den Login |
| `APP_SECRET_KEY` | Secret Key fuer Flask-Sessions |
| `DATA_DIR` | Speicherort der SQLite-Datenbank im Container |

Beispiel:

```yaml
environment:
  APP_PASSWORD: "dein-sicheres-passwort"
  APP_SECRET_KEY: "ein-langer-zufaelliger-secret-key"
```

## Daten und GitHub

Die echte Zeiterfassungsdatenbank gehoert nicht ins GitHub-Repository. Sie liegt im laufenden Betrieb im persistenten `data`-Ordner auf dem Server.

Das Repository enthaelt die App, Templates und Docker-Konfiguration. Persoenliche Daten wie `data/zeiterfassung.db` sollten lokal oder auf dem Server bleiben.

## Projektstruktur

```text
.
+-- app.py
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
+-- static/
|   +-- pdf/
+-- templates/
+-- data/
```

## Stand

Aktueller gesicherter Stand: `Version 1.1`

Die App ist fuer den privaten produktiven Einsatz gedacht und kann direkt ueber Docker oder Portainer betrieben werden.
