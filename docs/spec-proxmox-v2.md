# SPEC — Plugin Proxmox v2

**Fichier cible :** `core/infra/plugin.py`  
**Dépendances config :** `config.py` + `core/infra/proxmox_config.py` (nouveau)  
**Statut actuel :** plugin existant, mono-instance, sans PBS, sans affectation société  
**Objectif :** multi-instance · PBS · profils · affectation univers/société/tag

---

## 1. Modèle de données — `proxmox_config.py`

Ce fichier remplace les constantes hardcodées dans `config.py`.  
Il est chargé dynamiquement par le plugin, modifiable depuis l'UI Paramètres.

### 1.1 Structure d'une instance Proxmox

```python
PROXMOX_INSTANCES = [
    {
        "id": "pve-opent",                  # identifiant interne unique (slug)
        "label": "Proxmox OpenTechno",      # nom affiché dans l'UI
        "host": "192.168.1.10",
        "port": 8006,
        "user": "root@pam",
        "token_name": "ada",
        "token_value": "xxxx-xxxx-xxxx",
        "verify_ssl": False,
        "enabled": True,

        # Affectation : univers + société (optionnel) + tag libre
        "universe": "opent",               # opent | home | uscss | margep
        "company_id": "opentechno",        # slug société, None si "Maison"
        "tags": ["infra", "production"],   # tags libres pour filtrage

        # PBS associé à cette instance (optionnel)
        "pbs_id": "pbs-opent",             # ref vers une entrée PBS_INSTANCES, ou None
    },
    {
        "id": "pve-home",
        "label": "Proxmox Maison",
        "host": "192.168.1.20",
        "port": 8006,
        "user": "root@pam",
        "token_name": "ada",
        "token_value": "yyyy-yyyy-yyyy",
        "verify_ssl": False,
        "enabled": True,
        "universe": "home",
        "company_id": None,
        "tags": ["homelab"],
        "pbs_id": None,
    },
]
```

### 1.2 Structure d'une instance PBS (Proxmox Backup Server)

```python
PBS_INSTANCES = [
    {
        "id": "pbs-opent",
        "label": "PBS OpenTechno",
        "host": "192.168.1.11",
        "port": 8007,
        "user": "root@pam",
        "token_name": "ada",
        "token_value": "zzzz-zzzz-zzzz",
        "verify_ssl": False,
        "enabled": True,
        "universe": "opent",
        "company_id": "opentechno",
        "tags": ["backup", "production"],
        # Datastores PBS disponibles (rempli dynamiquement au démarrage)
        "datastores": [],
    },
]
```

### 1.3 Profils de backup

```python
PROXMOX_BACKUP_PROFILES = [
    {
        "id": "nightly-prod",
        "label": "Nuit — Production",
        "storage": "pbs-opent",           # id d'un PBS_INSTANCE ou nom de storage local
        "compress": "zstd",               # zstd | lzo | gzip | none
        "mode": "snapshot",               # snapshot | suspend | stop
        "retention": {
            "keep_last": 3,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 3,
        },
        "schedule": "0 2 * * *",          # cron (info seulement, exécuté côté PVE)
        "universe": "opent",
        "tags": ["production"],
    },
    {
        "id": "weekly-homelab",
        "label": "Hebdo — Homelab",
        "storage": "local",
        "compress": "zstd",
        "mode": "snapshot",
        "retention": {
            "keep_last": 2,
            "keep_weekly": 2,
        },
        "schedule": "0 3 * * 0",
        "universe": "home",
        "tags": ["homelab"],
    },
]
```

---

## 2. Plugin — `core/infra/plugin.py`

### 2.1 Changements structurels

Le plugin charge `proxmox_config.py` au démarrage et expose **toutes les instances activées** au LLM et à l'UI. Le `get_system_prompt_injection()` liste dynamiquement les instances disponibles avec leurs labels.

```python
def get_system_prompt_injection(self, context_id: str | None = None) -> str:
    # Filtre les instances selon le contexte actif (univers ou société)
    instances = self._get_instances_for_context(context_id)
    instance_list = "\n".join(
        f"  - {i['id']} : {i['label']} ({i['host']}) — tags: {', '.join(i['tags'])}"
        for i in instances
    )
    pbs_list = "\n".join(
        f"  - {p['id']} : {p['label']} ({p['host']})"
        for p in self._get_pbs_for_context(context_id)
    )
    profiles = "\n".join(
        f"  - {pr['id']} : {pr['label']} (storage: {pr['storage']}, rétention: {pr['retention']})"
        for pr in PROXMOX_BACKUP_PROFILES
        if not context_id or pr.get('universe') == context_id
    )
    return f"""
Tu gères l'infrastructure Proxmox (multi-instance).
Instances disponibles :
{instance_list}

Serveurs PBS disponibles :
{pbs_list or "  Aucun PBS configuré"}

Profils de backup disponibles :
{profiles or "  Aucun profil défini"}

Fonctions disponibles : vm_list, vm_power, vm_backup, vm_snapshot, vm_restore,
                        node_reboot, node_stats, storage_status,
                        pbs_status, pbs_backup_run, pbs_restore, backup_list.

RÈGLES :
- vm_power (stop/reboot), vm_backup, vm_snapshot, vm_restore, node_reboot,
  pbs_backup_run, pbs_restore : TOUJOURS demander confirmation avant exécution.
- Si l'utilisateur ne précise pas l'instance et qu'il y en a plusieurs dans le contexte,
  demande sur quelle instance il veut agir.
- node_reboot : avertir que toutes les VMs du node seront impactées.
    """.strip()
```

### 2.2 Méthode de filtrage par contexte

```python
def _get_instances_for_context(self, context_id: str | None) -> list[dict]:
    """
    Retourne les instances Proxmox pertinentes selon le contexte actif.
    context_id peut être un univers ('opent', 'home'...) ou un company_id.
    """
    if context_id is None:
        return [i for i in PROXMOX_INSTANCES if i["enabled"]]
    return [
        i for i in PROXMOX_INSTANCES
        if i["enabled"] and (
            i["universe"] == context_id or
            i["company_id"] == context_id or
            context_id in i.get("tags", [])
        )
    ]
```

---

## 3. Nouvelles fonctions exposées au LLM

### Fonctions Proxmox existantes (à conserver, enrichir avec `instance_id`)

| Fonction | Params ajoutés | confirm |
|---|---|---|
| `vm_list` | + `instance_id: str?` | non |
| `vm_power` | + `instance_id: str` | **oui** |
| `vm_backup` | + `instance_id: str`, `profile_id: str?` | **oui** |
| `vm_snapshot` | + `instance_id: str` | **oui** |
| `vm_restore` | + `instance_id: str` | **oui** |
| `node_reboot` | + `instance_id: str` | **oui** |
| `node_stats` | + `instance_id: str?` | non |
| `storage_status` | + `instance_id: str?` | non |

### Nouvelles fonctions PBS

```python
{
    "name": "pbs_status",
    "description": "Affiche l'état d'un serveur PBS : datastores, jobs actifs, espace utilisé.",
    "parameters": {
        "pbs_id": "string?  — id de l'instance PBS (tous si absent)",
    },
    "x_confirm_required": False,
},
{
    "name": "pbs_backup_run",
    "description": "Déclenche un backup PBS immédiat selon un profil défini. CONFIRMATION REQUISE.",
    "parameters": {
        "vmid":       "integer — ID de la VM/LXC à sauvegarder",
        "instance_id":"string  — instance Proxmox source",
        "pbs_id":     "string  — instance PBS cible",
        "profile_id": "string? — profil de backup (rétention, compression)",
    },
    "x_confirm_required": True,
    "x_confirm_message":  "Lancer le backup PBS de la VM {vmid} vers {pbs_id} avec le profil {profile_id} ?",
    "x_confirm_cmd":      "proxmox-backup-client backup {vmid}.pxar:/ --repository {pbs_id}",
},
{
    "name": "pbs_restore",
    "description": "Restaure une VM depuis un backup PBS. CONFIRMATION REQUISE.",
    "parameters": {
        "vmid":        "integer — ID VM à restaurer",
        "snapshot_id": "string  — identifiant du snapshot PBS",
        "pbs_id":      "string  — instance PBS source",
        "instance_id": "string  — instance Proxmox cible",
        "target_vmid": "integer? — nouvel ID si on ne veut pas écraser",
    },
    "x_confirm_required": True,
    "x_confirm_message":  "Restaurer la VM {vmid} depuis le snapshot {snapshot_id} sur PBS {pbs_id} ? Cette opération écrasera la VM existante.",
    "x_confirm_cmd":      "qmrestore {pbs_id}:{snapshot_id} {vmid} --force",
},
{
    "name": "backup_list",
    "description": "Liste les backups disponibles pour une VM, sur PBS ou sur le stockage local.",
    "parameters": {
        "vmid":        "integer? — filtrer par VM (tous si absent)",
        "instance_id": "string?  — instance Proxmox",
        "pbs_id":      "string?  — instance PBS (stockage local si absent)",
    },
    "x_confirm_required": False,
},
```

### Nouvelles fonctions multi-instance

```python
{
    "name": "proxmox_instances_list",
    "description": "Liste toutes les instances Proxmox configurées et leur état (online/offline).",
    "parameters": {
        "universe":   "string? — filtre par univers",
        "company_id": "string? — filtre par société",
        "tag":        "string? — filtre par tag",
    },
    "x_confirm_required": False,
},
```

---

## 4. Webhooks n8n — nouveaux endpoints

À ajouter dans `get_n8n_webhooks()` :

```python
"pbs-status":     "http://localhost:5678/webhook/pbs-status",
"pbs-backup-run": "http://localhost:5678/webhook/pbs-backup-run",
"pbs-restore":    "http://localhost:5678/webhook/pbs-restore",
"backup-list":    "http://localhost:5678/webhook/backup-list",
```

> **Note :** le payload de chaque webhook inclut désormais `instance_id` et `pbs_id` pour que n8n sache vers quelle machine router la commande.

---

## 5. UI Paramètres — onglet Proxmox

Dans la page Paramètres > Plugins > Infrastructure, ajouter un onglet de gestion des instances.

### 5.1 Liste des instances Proxmox

```
┌─────────────────────────────────────────────────────┐
│ Instances Proxmox                  [+ Ajouter]       │
├─────────────────────────────────────────────────────┤
│ 🟢 pve-opent  · OpenTechno  · opent · [infra, prod] │ [✎][🗑]
│ 🟢 pve-home   · Maison      · home  · [homelab]     │ [✎][🗑]
└─────────────────────────────────────────────────────┘
```

Chaque ligne affiche : statut live (ping), id, label, univers, tags, boutons édition/suppression.

### 5.2 Formulaire d'instance (inline)

```
Nom         [________________]
Host        [________________]   Port [8006]
User        [________________]   Token Name [____]
Token Value [________________________]   [ ] Vérifier SSL

Univers     [opent ▾]     Société [OpenTechno ▾]
Tags        [infra] [production] [+ ajouter tag]

PBS associé [pbs-opent ▾] ou [Aucun]

[Tester la connexion]    [Annuler]    [Enregistrer]
```

`Tester la connexion` : appel `GET /api/proxmox/test?instance_id=xxx` → retourne version + nb nodes.

### 5.3 Liste des instances PBS (même logique)

```
┌─────────────────────────────────────────────────────┐
│ Instances PBS                      [+ Ajouter]       │
├─────────────────────────────────────────────────────┤
│ 🟢 pbs-opent  · PBS OpenTechno · opent · [backup]   │ [✎][🗑]
└─────────────────────────────────────────────────────┘
```

### 5.4 Profils de backup

```
┌─────────────────────────────────────────────────────┐
│ Profils de backup                  [+ Ajouter]       │
├─────────────────────────────────────────────────────┤
│ nightly-prod   · Nuit Production · pbs-opent · opent │ [✎][🗑]
│ weekly-homelab · Hebdo Homelab   · local     · home  │ [✎][🗑]
└─────────────────────────────────────────────────────┘
```

Formulaire profil :
```
Nom         [________________]
Storage     [pbs-opent ▾]   (liste les PBS + storages locaux des PVE actifs)
Compression [zstd ▾]
Mode        [snapshot ▾]
Rétention   last [3]  daily [7]  weekly [4]  monthly [3]
Schedule    [0 2 * * *]   (info seulement)
Univers     [opent ▾]   Tags [production] [+ tag]
```

---

## 6. KPIs dashboard — évolution

Le widget KPI Proxmox devient multi-instance :

```python
# Avant (mono)
{ "id": "prox_nodes", "label": "Nodes online", "value": "2/2" }

# Après (multi)
{ "id": "prox_nodes", "label": "Nodes online", "value": "4/4",
  "detail": "pve-opent: 2/2 · pve-home: 2/2" }
{ "id": "prox_pbs",   "label": "PBS",          "value": "1/1",
  "detail": "pbs-opent: OK · 380GB libre" }
```

---

## 7. Utterances semantic_router — ajouts

```python
# Nouveaux termes PBS
"pbs", "proxmox backup server", "datastore", "backup pbs",
"restauration", "restore", "point de restauration",
"retention", "rétention backup",

# Multi-instance
"quelle instance", "sur quel proxmox", "les deux proxmox",
"proxmox maison", "proxmox opentechno",
```

---

## 8. Fichiers à créer / modifier

| Fichier | Action |
|---|---|
| `core/infra/proxmox_config.py` | **Créer** — modèle de données instances PVE + PBS + profils |
| `core/infra/plugin.py` | **Modifier** — multi-instance, PBS, filtrage contexte, nouvelles fonctions |
| `core/infra/proxmox_client.py` | **Créer** — client HTTP Proxmox API REST (proxmoxer ou httpx) |
| `core/infra/pbs_client.py` | **Créer** — client PBS API REST |
| `web/routes_infra.py` | **Modifier** — ajouter routes `/api/proxmox/test`, `/api/pbs/status` |
| `config.py` | **Modifier** — retirer les constantes Proxmox hardcodées, importer proxmox_config |

---

## 9. Ce qui ne change PAS

- La mécanique `x_confirm_required` / `x_confirm_cmd` — déjà en place, rien à toucher
- Le système de routing `semantic_router` → `function_gemma` — on ajoute juste des utterances
- Les webhooks n8n existants — on les garde, on en ajoute de nouveaux
- Le `BasePlugin` et `plugin_registry` — interface inchangée
