# Changelog

## Version 1.12 - 2026-06-21

- Automatischen Änderungsverlauf für Tages-Autosaves, Schnellstempel und komplette Wochenvorlagen ergänzt.
- Einzelne Vorgänge können auf einer eigenen Verlaufsseite gezielt wiederhergestellt werden; auch die Wiederherstellung selbst wird protokolliert.
- Wochenvorlagen verlangen vor dem Überschreiben eine Bestätigung.
- KW-Ansicht zeigt Montag bis Sonntag vollständig über Monatsgrenzen hinweg und berücksichtigt alle sieben Tage in der Wochenberechnung.
- Wochenvorlagen werden ebenfalls über Monatsgrenzen auf die vollständige Kalenderwoche angewendet.

## Version 1.11 - 2026-06-11

- PDF-Stundenzettel schreibt bei Sommerschicht rechts in die Spalte `Bemerkungen` den Eintrag `Sommerschicht`.

## Version 1.10 - 2026-06-10

- PDF-Stundenzettel ergänzt links in den Tageszeilen die Wochentagskürzel Mo bis So.
- Gleitzeitkonto rechnet Monats- und Gesamtstände automatisch erst ab Mai 2026; ältere Daten bleiben gespeichert, werden aber nicht mehr eingerechnet.
- Vorlage unten auf `+/- Stunden Vormonate` angepasst.
- Mobile Zeiterfassung ordnet die acht Kennzahlen unter dem Arbeitsbereich an, damit Tageserfassung und Kalender schneller erreichbar sind.

## Version 1.9 - 2026-05-30

- Sichtbare deutsche Texte auf echte Umlaute umgestellt, unter anderem März, Frühschicht, Spätschicht und Monatsübersicht.
- Gleitzeit-Tagesauswahl springt nach dem Klick direkt zur Eingabe und nutzt kein altes Scroll-Restore mehr.

## Version 1.8 - 2026-05-30

- Stundenzettel-Oberfläche neu strukturiert: Kopfzeile, Kennzahlen, Tageserfassung und Kalender sind klarer getrennt.
- Mobile Ansicht sachlicher aufgebaut, damit Tagesauswahl, Saldo und Aktionen schneller auffindbar sind.
- Optik reduziert: weniger Glas-Effekt, kleinere Rundungen, ruhigere Karten und kompaktere Buttons.
- Bestehende Berechnung, Speicherung, Gleitzeitlogik und PDF-Funktionen unverändert gelassen.

## Version 1.7 - 2026-05-30

- Bezeichnung der laufenden Gleitzeit-Summe auf "Gesamtstand" geändert.
- Gleitzeit-Oberfläche, Autosave-Anzeige, PDF-Export und Dokumentation verwenden jetzt dieselbe Bezeichnung.

## Version 1.6 - 2026-05-30

- Gleitzeit-Tagesformular speichert jetzt per Autosave und aktualisiert Tages-, Monats- und Jahressummen direkt in der Ansicht.
- Gleitzeitkonto übernimmt die Monats-Plus-/Minusstunden automatisch aus der normalen Zeiterfassung.
- Genommene Gleitzeit wird vom jeweiligen Monatswert abgezogen und im Gesamtstand bis zum gewählten Monat zusammengeführt.
- Gleitzeit-PDF zeigt Zeiterfassung, Korrektur, genommene Gleitzeit, Monatssaldo und Gesamtstand.

## Version 1.5 - 2026-05-30

- Gleitzeitkonto speichert Monats- und Tagesänderungen automatisch während der Eingabe.
- Speichern-Buttons bleiben als manuelle Sicherung sichtbar.
- Gelbe Markierung des aktuellen Monats im Gleitzeit-PDF entfernt.

## Version 1.4 - 2026-05-30

- Bestehender Stundenzettel bleibt unverändert, nur der automatische Vormonatsübertrag im PDF bleibt leer.
- Separates Gleitzeitkonto als eigener Bereich mit Jahres-, Monats- und Tagesansicht hinzugefügt.
- Gleitzeitkonto speichert manuelle Monatsstände sowie Tagesdetails zu Arbeitszeit und genommener Gleitzeit.
- Separater PDF-Export für das Gleitzeitkonto hinzugefügt.

## Version 1.3 - 2026-05-30

- Sommerschicht kann jetzt auch am Freitag ausgewählt werden.
- Freitag-Sommerschicht speichert die eingetragenen Zeiten nur dokumentarisch.
- Freitag-Sommerschicht wird nicht in Sollzeit, Istzeit, Saldo oder Monats-/Wochenwerte eingerechnet.

## Version 1.2 - 2026-05-28

- Sommerschicht als neue Schichtart hinzugefügt.
- Sommerschicht gilt Montag bis Donnerstag von 06:45 bis 14:00 Uhr.
- Sommerschicht wird immer als voller Arbeitstag ohne Pause und ohne Plus-/Minusstunden abgerechnet.
- Freitag bleibt unverändert bei 06:45 bis 13:00 Uhr.
- PDF-Export auf die cleane Vorlage umgestellt.
- Name und Monat/Jahr im PDF-Header sauber auf die Vorlagenzeile ausgerichtet.

## Version 1.1

- Mobile Zeiterfassung mit Wochen-/Monatsansicht, Schichtlogik und PDF-Export.
