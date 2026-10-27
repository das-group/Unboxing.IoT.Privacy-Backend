# Unboxing IoT Privacy - Platform (Backend)

Projektwebseite: [https://iot-privacy.info/](https://iot-privacy.info/) 

## Einrichtung:

```bash
cp example.env .env
```

### Bearbeite Umgebungsvariablen in .env:

- RP_ID: Gültige Domain, benötigt für Passkeys (Standard: "iot-privacy.info")
- ORIGIN: Gültige URLs (Standard: "https://platform.iot-privacy.info")
- **Wichtig:** Wähle sichere, zufällige Datenbankzugangsdaten für
    - MONGO_USER
    - MONGO_PASS
    - MONGO_BASICAUTH_USER
    - MONGO_BASICAUTH_PASSWORD
- IPINFO_TOKEN: Gültiger Zugangstoken von https://ipinfo.io/
- ONEKEY_API_URL: Firmwareanalyseinstanz von ONEKEY (Standard: "https://app.eu.onekey.com/api")
- ONEKEY_API_TOKEN: Gültiger Zugangstoken von ONEKEY

Start der Instanz:
```bash
docker compose up -d
```

Aktualisierung der Instanz, nach einer Änderung:
```bash
docker compose down --rmi local
docker compose up -d
```