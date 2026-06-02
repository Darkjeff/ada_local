# SPEC — Connecteur Proxmox Backup Server (PBS)
**Périmètre :** couche web uniquement (`/web`) — pas de `main.py`, pas de `/gui`  
**Contexte :** OpenTechno · ADA local · branche `univers`  
**Statut erreur actuel :** `401 Unauthorized` sur `https://<host>:8007/api2/json/version`

---

## 1. Diagnostic — Pourquoi le 401

PBS n'est **pas** un Proxmox VE. Son API REST écoute sur le port **8007** mais son système d'authentification diffère sur deux points critiques :

| Point | Proxmox VE (8006) | Proxmox Backup Server (8007) |
|---|---|---|
| Realm par défaut | `pam` | `pam` (mais souvent `pbs` en prod) |
| Token format | `PVEAPIToken=USER@REALM!TOKENID=SECRET` | `PBSAPIToken=USER@REALM!TOKENID=SECRET` |
| Header auth | `Authorization: PVEAPIToken=...` | `Authorization: PBSAPIToken=...` |
| Ticket session | `/api2/json/access/ticket` | idem, mais realm doit matcher |

**Cause probable du 401 :** le connecteur actuel envoie soit le mauvais header (`PVEAPIToken` au lieu de `PBSAPIToken`), soit le realm est incorrect, soit les credentials utilisés sont des credentials PVE réutilisés sur PBS.

---

## 2. Ce qu'il faut dans `config.py`

Ajouter une section dédiée PBS, distincte de PVE :

```python
# --- Proxmox Backup Server (PBS) ---
PBS_HOST = "https://<ip_ou_hostname>:8007"
PBS_USER = "root@pam"           # ou un user dédié ex: ada@pbs
PBS_TOKEN_ID = "ada-token"      # nom du token API créé dans PBS
PBS_TOKEN_SECRET = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
PBS_VERIFY_SSL = False          # True si certificat valide
```

> **Ne pas réutiliser** `PROXMOX_HOST` / `PROXMOX_TOKEN` du bloc PVE — ce sont deux systèmes distincts.

---

## 3. Spec du module web `/web/connectors/pbs.py`

### 3.1 Authentification

PBS supporte deux modes — utiliser **API Token** (stateless, recommandé pour ADA) :

```
GET https://<host>:8007/api2/json/version
Headers:
  Authorization: PBSAPIToken=root@pam!ada-token:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Le format du header est strict : `PBSAPIToken=<user>@<realm>!<tokenid>:<secret>`

### 3.2 Créer le token dans PBS (côté admin — prérequis)

1. PBS Web UI → `Configuration` → `User Management` → sélectionner l'user
2. Onglet `API Tokens` → `Add`
3. Noter le secret **une seule fois** (non récupérable ensuite)
4. Assigner le privilège minimum : `Datastore.Audit` pour lecture, `Datastore.Backup` pour déclencher des jobs

### 3.3 Endpoints utiles pour ADA

| Fonction ADA | Endpoint PBS | Méthode |
|---|---|---|
| Vérifier connexion | `/api2/json/version` | GET |
| Lister les datastores | `/api2/json/admin/datastore` | GET |
| Lister les snapshots d'un datastore | `/api2/json/admin/datastore/{store}/snapshots` | GET |
| Statut des jobs de backup | `/api2/json/admin/sync` ou `/api2/json/nodes/localhost/tasks` | GET |
| Déclencher un job de garbage collect | `/api2/json/admin/datastore/{store}/gc` | POST |
| Vérifier intégrité | `/api2/json/admin/datastore/{store}/verify` | POST |

### 3.4 Structure du connecteur

```
/web/
  connectors/
    pbs.py          ← nouveau fichier, spec ci-dessous
    proxmox.py      ← existant (PVE, port 8006) — NE PAS MODIFIER
```

**Interface publique de `pbs.py` :**

```python
class PBSConnector:
    def __init__(self, host: str, user: str, token_id: str, token_secret: str, verify_ssl: bool = False)
    
    async def get_version(self) -> dict
    # Retourne {"version": "x.y.z", "release": "...", "repoid": "..."}
    # Utilisé comme healthcheck

    async def list_datastores(self) -> list[dict]
    # Retourne liste des datastores avec nom, path, total/used/available bytes

    async def list_snapshots(self, store: str, backup_type: str = None, backup_id: str = None) -> list[dict]
    # Filtre optionnel par type (vm/ct/host) et backup_id (vmid ou hostname)

    async def get_tasks(self, limit: int = 50, errors_only: bool = False) -> list[dict]
    # Tâches récentes — filtrées sur erreurs si errors_only=True

    async def get_datastore_status(self, store: str) -> dict
    # Usage disque, nombre de snapshots, dernier GC
```

### 3.5 Gestion des erreurs

```python
# Mapper les codes HTTP PBS vers des exceptions ADA cohérentes
401 → PBSAuthError("Token invalide ou realm incorrect")
403 → PBSPermissionError("Privilège insuffisant sur le datastore")
404 → PBSNotFoundError("Datastore ou ressource introuvable")
500 → PBSServerError("Erreur interne PBS")
```

Loguer systématiquement `response.headers.get('x-proxmox-error')` — PBS y met des détails utiles.

---

## 4. Intégration dans la couche web ADA

### 4.1 Route API interne

```
GET  /api/infra/pbs/status          → healthcheck + datastores
GET  /api/infra/pbs/snapshots       → ?store=<name>&type=vm&id=<vmid>
GET  /api/infra/pbs/tasks           → ?errors_only=true&limit=20
```

### 4.2 Affichage dans `ada-interface.html`

Dans le tab `#tab-infra`, ajouter une section PBS distincte de la grille PVE :

```
[ Section : Proxmox Backup Server ]
  ├── Nœud PBS · <host> · ● Online / ✕ Auth Error
  ├── Datastore : backup-nas  →  14.2 / 20 TB  (71%)
  ├── Snapshots : 142 entrées · dernier 05:47
  └── Tâches récentes : ✓ 18/18 · ⚠ 0 erreur
```

Le node PBS dans `infra-grid` doit afficher `.warn` si :
- Auth échoue (401/403)
- Un datastore dépasse 80% d'usage
- Une tâche récente est en erreur

### 4.3 Message ADA sur erreur 401

Quand `PBSConnector.get_version()` retourne `PBSAuthError`, ADA affiche dans le chat :

> ⚠ **PBS OpenTechno — Erreur d'authentification**  
> Connexion refusée sur `<host>:8007`. Vérifie le token API PBS (format `PBSAPIToken=`, realm `pam` ou `pbs`) et les privilèges du compte.

---

## 5. Checklist de mise en œuvre

- [ ] Créer le token API dans l'interface PBS (Web UI port 8007)
- [ ] Ajouter `PBS_*` vars dans `config.py` (section séparée PVE)
- [ ] Créer `/web/connectors/pbs.py` selon l'interface 3.4
- [ ] Vérifier que `Authorization` header utilise `PBSAPIToken=` (pas `PVEAPIToken=`)
- [ ] Tester `GET /api2/json/version` avec curl avant d'intégrer :
  ```bash
  curl -k -H "Authorization: PBSAPIToken=root@pam!ada-token:<secret>" \
    https://<host>:8007/api2/json/version
  ```
- [ ] Ajouter routes `/api/infra/pbs/*` dans le router web
- [ ] Mettre à jour `ada-interface.html` section infra-grid
- [ ] Ajouter nœud PBS dans le flux alertes si auth KO

---

## 6. Note sécurité

- Le token PBS doit avoir les **privilèges minimum** nécessaires (principe de moindre privilège)
- `PBS_VERIFY_SSL = False` acceptable en LAN privé, à passer `True` si PBS derrière reverse proxy TLS valide
- Ne pas stocker `PBS_TOKEN_SECRET` en clair dans le repo — utiliser `.env` ou un vault
