# ADA — Webhook entrant

**Fichier source :** `web/router_webhook.py`  
**Préfixe URL :** `/api/webhook/`  
**Méthode :** `POST`

Permet à n'importe quel service externe (Domoticz, n8n, Home Assistant, Zigbee2MQTT, scripts custom…) d'envoyer des commandes ou événements à ADA.

---

## Table des matières

1. [Récupérer le token](#1-récupérer-le-token)
2. [Authentification](#2-authentification)
3. [Point d'entrée principal](#3-point-dentrée-principal)
4. [Modes de traitement](#4-modes-de-traitement)
   - [Mode intent texte](#41-mode-intent-texte--réponse-ada)
   - [Mode action directe](#42-mode-action-directe)
   - [Mode événement](#43-mode-événement-fire--forget)
5. [Référence par source](#5-référence-par-source)
   - [Domoticz](#51-domoticz)
   - [n8n](#52-n8n)
   - [Home Assistant](#53-home-assistant)
   - [Zigbee2MQTT](#54-zigbee2mqtt)
   - [Script Python / curl](#55-script-python--curl)
6. [Rotation du token](#6-rotation-du-token)
7. [Codes de retour](#7-codes-de-retour)
8. [Sécurité](#8-sécurité)

---

## 1. Récupérer le token

Le token est généré automatiquement au premier démarrage d'ADA et persiste dans `settings.json`.

### Via l'API (authentifié JWT)

```http
GET /api/webhook/config
Authorization: Bearer <jwt_token>
```

Réponse :

```json
{
  "token": "qAgwvKavHNooQZdDnPtcPbgwNVA1_5SzboAUPuJEiEE",
  "endpoint": "/api/webhook/{source}",
  "auth": "query ?token=<secret>  |  header X-Webhook-Token  |  Authorization: Bearer <secret>",
  "sources_examples": ["domoticz", "n8n", "home_assistant", "alexa", "generic"],
  "payload_modes": { ... }
}
```

### Via curl (depuis le serveur local)

```bash
cd /home/aurelien/ada_local
venv/bin/python -c "from web.router_webhook import _get_or_create_token; print(_get_or_create_token())"
```

---

## 2. Authentification

Le token doit être transmis à **chaque requête**, via l'une de ces trois méthodes (par ordre de priorité) :

| Méthode | Exemple |
|---|---|
| Query parameter | `?token=qAgwvKavHNoo...` |
| Header dédié | `X-Webhook-Token: qAgwvKavHNoo...` |
| Authorization Bearer | `Authorization: Bearer qAgwvKavHNoo...` |

Une requête sans token ou avec un token invalide retourne `HTTP 401`.

---

## 3. Point d'entrée principal

```
POST /api/webhook/{source}
```

Le paramètre `{source}` est libre — il identifie l'expéditeur dans les logs et dans le Radar.  
Exemples valides : `domoticz`, `n8n`, `home_assistant`, `zigbee2mqtt`, `mon_script`.

**Content-Type attendu :** `application/json`

---

## 4. Modes de traitement

Le mode est déterminé automatiquement par la **structure du payload** :

```
payload contient "action"                → Mode action directe
payload contient "event" (sans texte)    → Mode événement
payload contient "text" / "message" / "query"  → Mode intent texte
```

---

### 4.1 Mode intent texte → réponse ADA

ADA traite le texte comme un message utilisateur via son pipeline complet (LLM + skills + contexte).  
La réponse est **synchrone** — attend la génération complète avant de retourner.

**Payload :**

```json
{
  "text": "Quel est la température extérieure ?",
  "history": [],
  "universe": "home"
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `text` | string | ✅ | Message à traiter par ADA |
| `message` | string | alias | Synonyme de `text` |
| `query` | string | alias | Synonyme de `text` (format Alexa/Google) |
| `history` | array | ❌ | Historique de conversation `[{role, content}]` |
| `universe` | string | ❌ | Contexte univers (`home`, `opent`, `uscss`, `margep`) |

**Réponse :**

```json
{
  "ok": true,
  "source": "domoticz",
  "text": "Quel est la température extérieure ?",
  "reply": "La température extérieure est de 18°C selon les données météo."
}
```

---

### 4.2 Mode action directe

Exécute une fonction via le `FunctionExecutor` sans passer par le LLM.  
Utile pour les automatisations déterministes.

**Payload :**

```json
{
  "action": "control_light",
  "params": {
    "room": "salon",
    "state": "on"
  }
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `action` | string | ✅ | Nom de la fonction à exécuter |
| `params` | object | ❌ | Paramètres passés à la fonction |

**Actions disponibles (exemples) :**

| Action | Params principaux |
|---|---|
| `control_light` | `room`, `state` (`on`/`off`) |
| `set_timer` | `duration_seconds`, `label` |
| `weather` | _(aucun)_ |
| `get_system_info` | _(aucun)_ |
| `web_search` | `query` |

**Réponse :**

```json
{
  "ok": true,
  "source": "n8n",
  "action": "control_light",
  "result": { "success": true, "message": "Lumière salon allumée" }
}
```

---

### 4.3 Mode événement (fire & forget)

Enregistre un événement dans le Radar d'ADA. La requête retourne immédiatement sans attendre le traitement.  
Idéal pour les notifications d'état (changement capteur, alerte, etc.).

**Payload :**

```json
{
  "event": "device_changed",
  "device": "lumiere_salon",
  "value": 1,
  "unit": "on/off"
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `event` | string | ✅ | Type d'événement (libre) |
| _autres_ | any | ❌ | Metadata libres, tous transmis au Radar |

> **Règle :** si le payload contient `event` **sans** aucun champ `text`/`message`/`query`, le mode événement est sélectionné.

**Réponse :**

```json
{
  "ok": true,
  "source": "domoticz",
  "event": "device_changed",
  "queued": true
}
```

---

## 5. Référence par source

### 5.1 Domoticz

Domoticz supporte les scripts LUA et dzVents pour déclencher des webhooks.

**Script dzVents (notification sur changement de device) :**

```lua
return {
    on = { devices = { 'Température Salon' } },
    execute = function(domoticz, device)
        local token = 'VOTRE_TOKEN_ICI'
        local url   = 'https://ADA_IP:7654/api/webhook/domoticz?token=' .. token
        local body  = '{"event":"temperature_changed","device":"' .. device.name
                      .. '","value":' .. device.temperature .. '}'
        domoticz.openURL({ url=url, method='POST',
                           headers={['Content-Type']='application/json'}, postData=body })
    end
}
```

**Script dzVents (commande texte vers ADA) :**

```lua
return {
    on = { devices = { 'Bouton Scène' } },
    execute = function(domoticz, device)
        if device.state == 'On' then
            local token = 'VOTRE_TOKEN_ICI'
            local url   = 'https://ADA_IP:7654/api/webhook/domoticz?token=' .. token
            local body  = '{"text":"Active la scène soirée cinéma"}'
            domoticz.openURL({ url=url, method='POST',
                               headers={['Content-Type']='application/json'}, postData=body })
        end
    end
}
```

> ⚠ Domoticz utilise des connexions HTTP simples par défaut. Si ADA tourne en HTTPS avec un certificat auto-signé, désactiver la vérification SSL dans les paramètres Domoticz ou utiliser un reverse proxy HTTP.

---

### 5.2 n8n

**Node : HTTP Request**

| Champ | Valeur |
|---|---|
| Method | `POST` |
| URL | `https://ADA_IP:7654/api/webhook/n8n` |
| Authentication | Header Auth → `X-Webhook-Token` : `<token>` |
| Body Content Type | `JSON` |

**Payload pour intent texte :**
```json
{
  "text": "={{ $json.message }}",
  "universe": "home"
}
```

**Payload pour événement :**
```json
{
  "event": "workflow_completed",
  "workflow": "={{ $workflow.name }}",
  "status": "success"
}
```

**Récupérer la réponse ADA** dans le nœud suivant via `{{ $json.reply }}`.

---

### 5.3 Home Assistant

**Automation YAML :**

```yaml
automation:
  - alias: "Notifier ADA — Température critique"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature_salon
        above: 28
    action:
      - service: rest_command.ada_webhook
        data:
          text: "La température du salon dépasse 28°C, que faire ?"

rest_command:
  ada_webhook:
    url: "https://ADA_IP:7654/api/webhook/home_assistant"
    method: POST
    headers:
      Content-Type: application/json
      X-Webhook-Token: "VOTRE_TOKEN_ICI"
    payload: '{"text": "{{ text }}"}'
    content_type: "application/json; charset=utf-8"
    verify_ssl: false
```

**Payload reconnu nativement (format HA) :**
```json
{ "text": "Allume les lumières du couloir" }
```

---

### 5.4 Zigbee2MQTT

Via un script Node.js branché sur le broker MQTT :

```javascript
const mqtt  = require('mqtt');
const fetch = require('node-fetch');
const https = require('https');

const ADA_TOKEN = 'VOTRE_TOKEN_ICI';
const ADA_URL   = 'https://ADA_IP:7654/api/webhook/zigbee2mqtt';
const agent     = new https.Agent({ rejectUnauthorized: false }); // cert auto-signé

const client = mqtt.connect('mqtt://localhost:1883');
client.subscribe('zigbee2mqtt/+');

client.on('message', async (topic, message) => {
    const device = topic.split('/')[1];
    const state  = JSON.parse(message.toString());

    await fetch(`${ADA_URL}?token=${ADA_TOKEN}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: 'state_changed', device, ...state }),
        agent,
    });
});
```

---

### 5.5 Script Python / curl

**curl — intent texte :**

```bash
TOKEN="qAgwvKavHNooQZdDnPtcPbgwNVA1_5SzboAUPuJEiEE"

curl -sk -X POST "https://localhost:7654/api/webhook/mon_script?token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "Donne-moi un résumé des tâches en cours"}' | python3 -m json.tool
```

**curl — événement :**

```bash
curl -sk -X POST "https://localhost:7654/api/webhook/cron" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: $TOKEN" \
  -d '{"event": "backup_completed", "host": "proxmox01", "duration_s": 142}'
```

**Python :**

```python
import httpx

ADA_URL   = "https://localhost:7654"
ADA_TOKEN = "qAgwvKavHNooQZdDnPtcPbgwNVA1_5SzboAUPuJEiEE"

# Intent texte
response = httpx.post(
    f"{ADA_URL}/api/webhook/mon_script",
    params={"token": ADA_TOKEN},
    json={"text": "Résume les alertes infrastructure"},
    verify=False,
)
print(response.json()["reply"])

# Événement
httpx.post(
    f"{ADA_URL}/api/webhook/monitoring",
    headers={"X-Webhook-Token": ADA_TOKEN},
    json={"event": "cpu_spike", "host": "srv-01", "value_pct": 95},
    verify=False,
)
```

---

## 6. Rotation du token

En cas de compromission ou de changement de configuration :

```http
POST /api/webhook/config/rotate
Authorization: Bearer <jwt_token>
```

**Réponse :**
```json
{
  "ok": true,
  "token": "NOUVEAU_TOKEN_32_CHARS..."
}
```

> ⚠ L'ancien token est invalidé **immédiatement**. Mettre à jour tous les services qui l'utilisent.

---

## 7. Codes de retour

| Code | Signification |
|---|---|
| `200` | Succès |
| `401` | Token manquant ou invalide |
| `422` | Payload non reconnu (aucun champ attendu trouvé) |
| `500` | Erreur interne ADA (voir logs `/tmp/ada_server.log`) |

**Structure d'erreur :**
```json
{ "detail": "Token webhook invalide ou manquant" }
```

---

## 8. Sécurité

| Point | Implémentation |
|---|---|
| Comparaison token | `hmac.compare_digest()` — résistant aux timing attacks |
| Token strength | `secrets.token_urlsafe(32)` — 256 bits d'entropie |
| Logs | Le token n'est jamais loggué (filtré dans les payloads) |
| Transport | HTTPS obligatoire en production (certificat dans `web/certs/`) |
| Bypass JWT | `/api/webhook/` est exempté du middleware JWT — son propre token fait office d'auth |
| Rotation | `POST /api/webhook/config/rotate` invalide l'ancien token instantanément |

### Recommandations

- Ne jamais passer le token en clair dans des logs Domoticz/n8n — utiliser la méthode header `X-Webhook-Token`
- En production, placer ADA derrière un reverse proxy (Nginx/Caddy) avec un certificat Let's Encrypt valide pour éviter les avertissements SSL
- Restreindre l'accès au port 7654 via firewall aux seules IP des services autorisés
