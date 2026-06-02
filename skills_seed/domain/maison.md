---
id: seed_domain_maison
name: Maison — Domotique et automatisation
domain: maison
priority: 2
summary: Contexte domotique maison, équipements et règles d'automatisation
---
## Contexte domotique

La maison est équipée d'un système domotique géré par Home Assistant.

## Équipements principaux

- **Lumières** : ampoules Zigbee (Philips Hue, IKEA Tradfri)
- **Chauffage** : thermostats connectés par pièce
- **Prises** : Kasa TP-Link pour les appareils pilotables
- **Capteurs** : température, humidité, mouvement, ouverture
- **Multimédia** : Kodi, Chromecast, enceintes Sonos

## Règles générales

- Les lumières du salon s'éteignent automatiquement après 23h30
- La présence est détectée par le Wi-Fi des téléphones
- Les scènes disponibles : "Cinéma", "Lecture", "Soirée", "Réveil"
- Les automatisations s'activent/désactivent via ADA

## Commandes courantes

- "Allume/éteins [pièce]" → contrôle lumières
- "Règle la température à [X]°" → thermostat
- "Active la scène [nom]" → scène prédéfinie
- "Quel est l'état de [appareil] ?" → statut en temps réel
