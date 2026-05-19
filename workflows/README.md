# ADA — Workflows n8n

Répertoire de stockage des workflows n8n utilisés par ADA.  
Chaque fichier JSON est un export direct depuis l'interface n8n (`Settings → Export`).

## Workflows disponibles

| Fichier | Webhook | Statut | Description |
|---|---|---|---|
| `shell-exec.json` | `POST /webhook/shell-exec` | ✅ Actif | Exécute une commande système et retourne stdout |
| `weather.json` | `POST /webhook/weather` | 🔧 À créer | Météo via OpenMeteo API (lat/lon d'Ennetières) |
| `web-search.json` | `POST /webhook/web-search` | 🔧 À créer | Recherche web via Brave Search API |
| `set-timer.json` | `POST /webhook/set-timer` | 🔧 À créer | Minuterie avec notification |
| `control-light.json` | `POST /webhook/control-light` | 🔧 À créer | Contrôle domotique (HA / Kasa) |
| `calendar-event.json` | `POST /webhook/calendar-event` | 🔧 À créer | Créer un événement Google Calendar |

## Format du payload ADA → n8n

Tous les webhooks reçoivent :
```json
{ "params": { ... } }
```

Et retournent :
```json
{ "success": true, "message": "texte lisible", "data": {} }
```

## Comment exporter un workflow depuis n8n

1. Ouvrir le workflow dans n8n
2. Menu `⋮` → `Download`
3. Sauvegarder le fichier JSON ici sous le nom `<action>.json`
4. Commiter : `git add workflows/<action>.json && git commit -m "feat(workflows): export <action>"`

## Coordonnées météo

- Ville : Ennetières-en-Weppes
- Latitude : `50.633331`
- Longitude : `2.95`
- Timezone : `Europe/Paris`
