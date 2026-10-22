# Portfolio-API: manuelles Deployment auf flos-server

Diese Dateien sind Vorlagen, nicht installiert. Kein Zugriff auf die VM wurde
vorgenommen. Ziel: Ubuntu 26.04, api.weimanndev.com -> 34.91.10.155,
Nginx -> 127.0.0.1:8001 -> Gunicorn/Flask. Coderr/Docker/Port 8000 bleiben unverändert.

## Architektur und Ressourcen

Ein Gunicorn-Master plus EIN synchroner Worker, ein Thread. Pro Worker wird nur
ein SMTP-Versand gleichzeitig bearbeitet. Timeout 60 s; SMTP-Socket-Timeout 10 s
je Operation (kein Gesamtzeitlimit). Nginx puffert Requests vor der Übergabe.
Gunicorn setzt PORTFOLIO_ENV=production ausdrücklich. Kein Entwicklungsserver,
kein Reload, keine Debug-Logs. Gunicorn-Zugriffslogs sind deaktiviert.

Planungswert, NICHT auf dieser VM gemessen: etwa 60–120 MiB zusätzlicher RAM für
Master + Worker + Python/SQLite, Lastspitzen möglich. Nginx läuft bereits.
549 MB Gesamt-RAM sind mit Coderr sehr knapp. Vor Installation freie/available
Speichermenge prüfen; bei zu wenig Reserve VM vergrößern, NICHT Coderr stoppen.
Keine Garantie, dass beide Anwendungen auf dieser VM stabil zusammenpassen.

Produktiv läuft KEIN Flask-Limiter-memory://. Statt Redis nutzen wir die
Python-Standardbibliothek SQLite, Transaktionen mit BEGIN IMMEDIATE und eine
private Datei unter /var/lib/portfolio-api. Grenzen: 5 POSTs/IP/Kalenderminute,
30 POSTs insgesamt/Kalenderstunde. Auch ungültige Anfragen zählen; OPTIONS nicht.
Es handelt sich um feste Zeitfenster: An Grenzen sind kurze Doppelbursts möglich.
Zähler bleiben bei Worker- und Dienstneustart erhalten. IP-Einträge werden bei
der nächsten Anfrage nach mehr als einer Stunde bereinigt; bei Inaktivität
bleiben sie bis dahin gespeichert. Es werden keine Nachrichten gespeichert.
Datenbankfehler führen zu 503, NICHT zu unbegrenztem Versand. Datendatei nicht
auf NFS und nicht öffentlich ablegen. Bei Überlastung kann die globale Grenze
auch legitime Anfragen blockieren. Diese kleine lokale Implementierung ist für
EINE VM gedacht und muss bei Skalierung durch einen gemeinsamen Dienst ersetzt werden.

Alternativen: Redis bietet bewährte gemeinsame Limits, braucht aber einen
weiteren Prozess, Python-Treiber und zusätzlichen RAM (mehrere bis einige zehn
MiB, abhängig von Konfiguration/Daten). Nginx-limit_req benötigt keinen neuen
Dienst, speichert Zähler aber flüchtig im Shared Memory. Daher hier SQLite.
Lokale Entwicklung verwendet weiterhin den bisherigen Flask-Limiter.

## Voraussetzungen MANUELL prüfen

- DNS A api.weimanndev.com auf 34.91.10.155; kein falscher AAAA-Eintrag.
- Frontend-Origin exakt https://weimanndev.com, ohne www und ohne Slash.
- Direkter Internetzugang zu Nginx, KEIN CDN/Load-Balancer davor.
- Bestehende Nginx-Konfiguration privat sichern und prüfen: kein vorhandener
  server_name api.weimanndev.com, keine globalen real_ip-Regeln, die beliebigen
  Clients vertrauen. Auch geerbte Auth-/Proxy-Regeln kontrollieren.
- Port 8001 frei; 8000/Docker/Coderr nicht ändern.
- Vorhandene Firewall muss HTTPS und die gewählte ACME-Prüfung erlauben.
  Keine Freigabe für 8001 nötig/erlaubt. Diese Anleitung ändert keine Firewall.

Lesende Prüfungen (Ausgaben können Betriebsdetails enthalten, nicht veröffentlichen):

```sh
free -m
sudo ss -ltnp
sudo nginx -t
sudo nginx -T
systemctl status nginx
```

## Dateien übertragen und Laufzeit installieren (erst später auf der VM)

Nur Quellcode, requirements.txt und deploy/ übertragen. KEINE lokale .env,
Windows-.venv, .git, Cache-Dateien oder produktive SQLite-Datei hochladen.
Die folgenden Befehle setzen voraus, dass das Backend unter /opt/portfolio-api
liegt; ein vorhandenes Verzeichnis vorher prüfen und nicht überschreiben.

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends python3-venv
sudo useradd --system --home-dir /opt/portfolio-api --shell /usr/sbin/nologin portfolio-api
sudo chown -R root:portfolio-api /opt/portfolio-api
sudo chmod -R g+rX,o-rwx /opt/portfolio-api
sudo python3 -m venv /opt/portfolio-api/.venv
sudo /opt/portfolio-api/.venv/bin/python -m pip install -r /opt/portfolio-api/requirements.txt
sudo /opt/portfolio-api/.venv/bin/python -m pip check
sudo install -d -m 700 /etc/portfolio-api
sudo install -m 600 /opt/portfolio-api/.env.example /etc/portfolio-api/portfolio.env
sudoedit /etc/portfolio-api/portfolio.env
```

Existiert der Service-Benutzer bereits, nicht erneut anlegen; Identität prüfen.
Die geschützte env-Datei manuell befüllen: PORTFOLIO_ENV=production,
ALLOWED_ORIGIN=https://weimanndev.com, RATE_LIMIT_DB=/var/lib/portfolio-api/rate-limits.sqlite3
und echte SMTP-/Empfängerwerte. Keine Zugangsdaten in Shell-Befehle schreiben.
Gmail-App-Passwort mit 2FA; MAIL_FROM_ADDRESS passend zum Konto.
SMTP_PORT=587 (STARTTLS), nicht 465. Keine FLASK_DEBUG- oder
GUNICORN_CMD_ARGS-Overrides hinzufügen. .env nicht ins App-Verzeichnis kopieren.

```sh
sudo install -m 644 /opt/portfolio-api/deploy/portfolio-api.service /etc/systemd/system/portfolio-api.service
sudo systemd-analyze verify /etc/systemd/system/portfolio-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-api
sudo systemctl status portfolio-api
sudo ss -ltnp
```

8001 muss NUR auf 127.0.0.1 lauschen. systemd erstellt /var/lib/portfolio-api
mit 0700 für den Dienst. Nginx ist der einzige vertrauenswürdige Reverse Proxy.
Es überschreibt X-Forwarded-For mit der Socket-Client-IP. ProxyFix vertraut
GENAU einer IP-/Protokoll-Station; Host/Port/Prefix werden nicht übernommen.
Eine äußere Middleware verwirft nichtlokale Socket-Peers vor ProxyFix.
Lokale Prozesse (einschließlich anderer kompromittierter VM-Anwendungen) bleiben
innerhalb dieser Vertrauensgrenze. Loopback ist keine Isolation gegen Coderr
bei einer vollständigen VM-Kompromittierung.

## Eigenen Nginx-vHost und Zertifikat vorbereiten

Zuerst ausschließlich die HTTP-Bootstrap-Datei aktivieren. Sie stellt nur
ACME-Dateien bereit und gibt sonst 404 zurück. Bestehende Coderr-Sites NICHT
ersetzen, deaktivieren oder als default_server verändern.

```sh
sudo install -d -m 755 /var/www/portfolio-acme
sudo install -m 644 /opt/portfolio-api/deploy/api.weimanndev.com.http.conf /etc/nginx/sites-available/portfolio-api
sudo ln -s /etc/nginx/sites-available/portfolio-api /etc/nginx/sites-enabled/portfolio-api
sudo nginx -t && sudo systemctl reload nginx
```

Wenn Dateiname/Symlink schon existiert, zuerst manuell prüfen, nicht überschreiben.
Vorhandenes Zertifikatswerkzeug nutzen; falls noch keines existiert, dessen
Installation getrennt planen. Beispiel mit bereits vorhandenem Certbot:

```sh
sudo certbot certonly --webroot -w /var/www/portfolio-acme -d api.weimanndev.com
```

Nur fortfahren, wenn Zertifikat und privater Schlüssel an den in der TLS-Vorlage
angegebenen Pfaden vorhanden sind. Ein bestehendes Zertifikat nicht ersetzen.

```sh
sudo install -m 644 /opt/portfolio-api/deploy/api.weimanndev.com.conf /etc/nginx/sites-available/portfolio-api
sudo nginx -t && sudo systemctl reload nginx
```

Zertifikatserneuerung und einen erfolgreichen Nginx-Reload nach Erneuerung mit
dem vorhandenen Zertifikatswerkzeug einrichten und prüfen. Nicht den vorhandenen
Coderr-Erneuerungsablauf überschreiben. Zertifikate/Logs/Geheimnisse nicht posten.

## Smoke-Tests OHNE E-Mail

```sh
curl -i -X OPTIONS https://api.weimanndev.com/api/contact -H 'Origin: https://weimanndev.com' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: Content-Type'
curl -i -X POST https://api.weimanndev.com/api/contact -H 'Origin: https://weimanndev.com' -H 'Content-Type: application/json' --data '{}'
```

Erwartung: Preflight erlaubt nur die exakte Origin; leere JSON-Anfrage liefert
422 ohne SMTP. Sechs ungültige POSTs innerhalb derselben Minute: sechster 429.
Mit wechselnden gefälschten X-Forwarded-For-Headern darf das Limit NICHT umgangen
werden. Neustart des Portfolio-Dienstes darf das Limit nicht zurücksetzen.
Diese Tests verbrauchen das Stundenbudget; bis zum nächsten Fenster warten.
Fremde Origin darf kein passendes Access-Control-Allow-Origin erhalten. CORS
ist kein Schutz gegen direkte HTTP-Clients. HTTP darf keine Kontaktanfragen
an Flask weiterleiten. Andere Pfade 404. Coderr vor/nach Reload separat prüfen.

Eine echte Mail erst nach ausdrücklicher Freigabe senden. Gmail-Kontolimits,
Zustellbarkeit, VM-SMTP-Ausgang und App-Passwort sind lokal nicht verifiziert.
Frontend muss separat auf https://api.weimanndev.com/api/contact eingestellt
werden; daran wurde hier nichts geändert.

## Betrieb, Datenschutz und Rückbau

```sh
sudo systemctl show portfolio-api -p MemoryCurrent
sudo journalctl -u portfolio-api --since today
free -m
```

Unter realistischer Last RAM gemeinsam mit Coderr messen. Kein automatisches
MemoryMax gesetzt, dessen willkürliche Grenze legitime Requests abbrechen könnte.
Fehlerlogs können IPs/URLs enthalten. Rotation/Retention für das separate
Nginx-Fehlerlog und das Journal bewusst festlegen; Datenschutzangaben um die
kurzlebigen SQLite-IP-Zähler ergänzen. Kein Nachrichteninhalt wird geloggt.
SQLite hat keine sichere Löschung auf physischem Datenträger garantiert.

Rückbau: nur portfolio-api stoppen/deaktivieren und dessen eigenen Nginx-Symlink
nach Prüfung entfernen; nginx -t vor Reload. Keine Coderr-Dateien anfassen.
Quellcode-Rollback ohne Löschen der Rate-Limit-Daten. Zertifikate anderer Sites
nicht ändern. Keine automatische Installation/Rückbau-Skripte enthalten.

## Lokale Prüfung und Grenzen

Vorhandene 16 plus 8 neue Tests prüfen CORS, SMTP-Mocks, Fehler, persistente
und atomare Limits sowie Proxy-Grenzen. Auf Windows wird Gunicorn bewusst nicht
installiert (Plattformmarker). Nginx-/systemd-Syntax und Linux-Gunicorn-Betrieb
müssen auf der VM mit den obigen Prüfungen bestätigt werden. Keine Serververbindung
wurde hergestellt; RAM-Angaben sind Schätzwerte. Ubuntu-/Python-Kompatibilität
der installierten Versionen muss beim späteren Installationsschritt bestätigt werden.
