# Zeiterfassung Docker

Eine schlanke, mobile Zeiterfassung für Schichtarbeit, gebaut für Docker, Portainer und den dauerhaften Betrieb auf einem NAS oder kleinen Server.

Die App ist darauf ausgelegt, Arbeitszeiten schnell am Handy einzutragen, Wochen und Monate sauber zu kontrollieren und am Ende einen fertigen Stundenzettel als PDF auszugeben.

## Funktionen

- Mobile Web-App für Handy, Tablet und Desktop
- Tagesansicht mit Schichtauswahl, Arbeitsbeginn, Arbeitsende und Notizfeld
- Wochenansicht und Monatsansicht mit schnellen Wechseln zwischen KW und Monat
- Wochenansicht zeigt Montag bis Sonntag vollständig, auch über Monatsgrenzen hinweg
- Frühschicht, Sommerschicht, Spätschicht, Freitag, Notdienst, Urlaub, Krank, Arztkrank, Feiertag und Frei
- Automatische Standardzeiten für Frühschicht, Sommerschicht, Spätschicht und Freitag
- Automatischer Pausenabzug bei Frühschicht
- Sommerschicht von Montag bis Donnerstag als voller Arbeitstag ohne Pausenabzug und ohne Plus-/Minusstunden
- Sommerschicht am Freitag ist dokumentarisch mit frei eintragbaren Zeiten und wird nicht gewertet
- Spätschicht startet standardmäßig um 11:55 Uhr und zählt die 5 Minuten Mehrarbeit mit
- Freitag wird immer als kurzer Arbeitstag behandelt
- Notdienst mit mehreren Zeitblöcken pro Tag
- Wochenend-Notdienst bleibt sichtbar, wird aber nicht in die normalen Wochen- und Monatsüberstunden eingerechnet
- Arztkrank kann mit Zeiten dokumentiert werden, ohne Arbeitszeit, Plusstunden oder Minusstunden zu beeinflussen
- Monatsübersicht mit Monats-Iststunden und Monatsüberstunden
- PDF-Export direkt in die hinterlegte Stundenzettel-Vorlage für Elisabeth
- PDF-Stundenzettel zeigt die Wochentagskürzel direkt neben den Tageszahlen
- Separates Gleitzeitkonto mit automatischem Monatsübertrag aus der Zeiterfassung, Gesamtstand und eigenem PDF-Export
- Gleitzeitkonto rechnet den automatischen Gesamtstand ab Mai 2026
- Automatischer Änderungsverlauf für Tages- und Wochenänderungen mit gezielter Wiederherstellung
- Wochenvorlagen verlangen vor dem Überschreiben eine Bestätigung
- Docker-Setup mit persistentem `data`-Ordner

## PDF-Export

Der PDF-Export füllt den Stundenzettel automatisch aus:

- Name und Monat werden oben eingetragen
- Frühschicht landet im Bereich `Anwesenheit Vormittag`
- Sommerschicht landet im Bereich `Anwesenheit Vormittag`
- Spätschicht landet im Bereich `Anwesenheit Nachmittag`
- Sommerschicht wird zusätzlich rechts in `Bemerkungen` ausgewiesen
- Notdienst kann Vormittag und Nachmittag getrennt darstellen
- Weitere Notdienst-Zeiten werden in `Bemerkungen` notiert
- Sondertage wie Urlaub, Krank, Arztkrank und Feiertag erscheinen in `Bemerkungen`
- Im Feld `Gesamt` steht die Kernarbeitszeit des Tages
- Bei Abweichungen steht dahinter der Saldo, zum Beispiel `07:45 = +00:05`
- Unten werden Monats-Saldo, Vormonate und aktueller Stand zusammengefasst

## Schichtlogik

| Typ | Standardzeit | Wertung |
| --- | --- | --- |
| Frühschicht | 06:45 - 15:00 | 7:45 Stunden, 30 Minuten Pause automatisch abgezogen |
| Sommerschicht | 06:45 - 14:00 | Montag bis Donnerstag 7:15 Stunden als voller Arbeitstag ohne Pause; Freitag frei eintragbar ohne Wertung |
| Spätschicht | 11:55 - 19:00 | 7:00 Stunden Soll plus 5 Minuten Mehrarbeit |
| Freitag | 06:45 - 13:00 | kurzer Freitag ohne Pause |
| Notdienst | frei eintragbar | zählt als Stunden, Wochenend-Notdienst nicht in Gesamtüberstunden |
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

Im Container läuft die App auf Port `8080`; die mitgelieferte `docker-compose.yml` veröffentlicht sie lokal auf Port `8091`.

## Portainer / NAS

1. Repository oder Projektordner auf den Server legen.
2. In Portainer einen neuen Stack anlegen.
3. Inhalt der `docker-compose.yml` verwenden.
4. Stack deployen.
5. App über Port `8091` oder über einen Reverse Proxy öffnen.

Die Datenbank liegt persistent im Ordner:

```text
data/zeiterfassung.db
```

Durch das Docker-Volume `./data:/app/data` bleibt die Datenbank auch nach Container-Neustarts erhalten.

## Konfiguration

Die wichtigsten Umgebungsvariablen:

| Variable | Beschreibung |
| --- | --- |
| `APP_PASSWORD` | Passwort für den Login |
| `APP_SECRET_KEY` | Secret Key für Flask-Sessions |
| `DATA_DIR` | Speicherort der SQLite-Datenbank im Container |

Beispiel:

```yaml
environment:
  APP_PASSWORD: "dein-sicheres-passwort"
  APP_SECRET_KEY: "ein-langer-zufälliger-secret-key"
```

## Daten und GitHub

Die echte Zeiterfassungsdatenbank gehört nicht ins GitHub-Repository. Sie liegt im laufenden Betrieb im persistenten `data`-Ordner auf dem Server.

Das Repository enthält die App, Templates und Docker-Konfiguration. Persönliche Daten wie `data/zeiterfassung.db` sollten lokal oder auf dem Server bleiben.

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

Aktueller gesicherter Stand: `Version 1.12`

Die Änderungen pro Version stehen in [CHANGELOG.md](CHANGELOG.md).

Die App ist für den privaten produktiven Einsatz gedacht und kann direkt über Docker oder Portainer betrieben werden.
