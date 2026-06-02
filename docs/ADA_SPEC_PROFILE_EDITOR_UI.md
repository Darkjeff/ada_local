# ADA — Spécification : Interface de configuration des profils

**Dépend de :** `ADA_SPEC_PROFILES_UNIVERSES.md`
**Fichiers cibles :** `web/static/views/profile-editor/`
**Branche :** `integration-n8n`
**Date :** 2026-05-31

---

## 1. Objectif

Permettre à l'admin de configurer depuis l'interface web :

1. Les **univers** — créer, nommer, colorer, choisir quels modules dedans, réordonner
2. Les **profils d'affichage** — créer, choisir les univers inclus, thème, densité, univers par défaut
3. L'**assignation device → profil** — chaque device enregistré peut recevoir un profil

Accessible uniquement aux utilisateurs du groupe `admin`.

---

## 2. Intégration dans l'existant

### 2.1 Enregistrement de la vue dans `core.js`

Ajouter dans `VIEW_LOADERS` :

```javascript
'profile-editor': () => import('/static/views/profile-editor/index.js'),
```

Ajouter dans `VIEW_TITLES` :

```javascript
'profile-editor': 'Profils & Univers',
```

### 2.2 Entrée dans la nav `index.html`

Ajouter dans la `<ul class="nav-list">`, dans le groupe admin (après Settings) :

```html
<li class="nav-item" data-view="profile-editor">
  <img src="/static/icons/Layout_white.svg" class="nav-icon-img" />
  <span>Profils</span>
</li>
```

**Note :** cette entrée doit être masquée pour les non-admins via `applyPermissions()`.
Ajouter `"profile-editor"` dans `PERMISSION_GROUPS["admin"]` dans `web/auth_permissions.py`.

### 2.3 Pattern de la vue (coller à l'existant)

Chaque vue exporte `mount(viewport, opts)` et optionnellement `unmount()`.
Le CSS est injecté dynamiquement comme dans `settings/index.js` :

```javascript
const _CSS = '/static/views/profile-editor/style.css';
function _ensureCSS() {
  if (!document.getElementById('css-profile-editor')) {
    const l = document.createElement('link');
    l.id = 'css-profile-editor'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}
```

---

## 3. Structure de la vue

La vue est divisée en **3 onglets** (même pattern que `settings/index.js`) :

```
┌─────────────────────────────────────────────────────┐
│  [Univers]   [Profils]   [Appareils]                 │  ← tab bar
├─────────────────────────────────────────────────────┤
│                                                     │
│  Contenu de l'onglet actif                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 4. Onglet 1 — Univers

### 4.1 Vue liste

```
┌─────────────────────────────────────────────────────┐
│ Univers                              [+ Nouvel univers] │
├─────────────────────────────────────────────────────┤
│ ● Dashboard   #00c8f0   dashboard, chat        [✎] [🗑] │
│ ● Maison      #8870ff   home, cameras, senses  [✎] [🗑] │
│ ● Société     #00e898   infrastructure, societe [✎] [🗑] │
└─────────────────────────────────────────────────────┘
```

Chaque ligne :
- Pastille colorée (couleur de l'univers)
- Nom de l'univers
- Code couleur hex
- Liste des modules (labels courts, séparés par virgule, tronqués à 40 chars)
- Bouton ✎ → ouvre le panneau d'édition inline
- Bouton 🗑 → confirmation + suppression (désactivé si l'univers est utilisé par un profil)

### 4.2 Panneau d'édition inline (expand sous la ligne)

S'ouvre quand on clique ✎ ou "+ Nouvel univers". Remplace la ligne courante.

```
┌─────────────────────────────────────────────────────┐
│ Nom          [________________]                     │
│ Icône        [◈ ▾]  (picker emoji/texte)            │
│ Couleur      [████] #00c8f0  (color input)          │
│                                                     │
│ Modules disponibles          Modules sélectionnés   │
│ ┌──────────────────┐         ┌────────────────────┐ │
│ │ ○ Tableau de bord│  ──►    │ ● Tableau de bord  │ │
│ │ ○ Discussion     │         │ ● Discussion       │ │
│ │ ○ Domotique      │         │ ↕ (drag to reorder)│ │
│ │ ○ Caméras        │  ◄──    └────────────────────┘ │
│ └──────────────────┘                                │
│ Groupés par catégorie : Core / Maison / Société /   │
│                         Transversal / Outils        │
│                                                     │
│              [Annuler]           [Enregistrer]      │
└─────────────────────────────────────────────────────┘
```

**Comportement des modules :**
- Liste de gauche = modules disponibles non encore sélectionnés, groupés par catégorie
- Liste de droite = modules sélectionnés, ordonnés (drag & drop avec `draggable`)
- Clic sur un module à gauche → le déplace à droite
- Clic sur un module à droite → le retire
- L'ordre de la liste de droite détermine `position` dans `universe_modules`
- Les modules filtrés par `requires_module` (ex: `societe`) n'apparaissent que si le flag est actif

**Validation :**
- Nom requis (non vide)
- Au moins 1 module sélectionné
- Couleur valide hex (#xxxxxx)

**API appelée :**
- Création : `POST /api/universes`
- Modification : `PUT /api/universes/{id}`

---

## 5. Onglet 2 — Profils

### 5.1 Vue liste

```
┌──────────────────────────────────────────────────────────┐
│ Profils d'affichage                   [+ Nouveau profil]  │
├──────────────────────────────────────────────────────────┤
│ Complet     dark · normal    Dashboard, Maison, Société… [✎][🗑] │
│ Mobile      dark · compact   Dashboard                   [✎][🗑] │
│ Maison      light · comfortable  Dashboard, Maison       [✎][🗑] │
└──────────────────────────────────────────────────────────┘
```

Chaque ligne :
- Nom du profil
- Thème + densité (ex: `dark · compact`)
- Liste des univers inclus (noms, séparés par virgule)
- Boutons ✎ et 🗑 (🗑 désactivé si des devices utilisent ce profil)

### 5.2 Panneau d'édition inline

```
┌──────────────────────────────────────────────────────────┐
│ Nom            [________________]                        │
│ Thème          [dark ▾]   dark | light | midnight | graphite │
│ Densité        [normal ▾] compact | normal | comfortable │
│                                                          │
│ Univers disponibles         Univers inclus (ordonnés)    │
│ ┌────────────────────┐      ┌──────────────────────────┐ │
│ │ ○ Planification    │ ──►  │ ● Dashboard              │ │
│ │ ○ Outils           │      │ ● Maison                 │ │
│ │                    │ ◄──  │ ● Société                │ │
│ └────────────────────┘      │ ↕ (drag to reorder)      │ │
│                             └──────────────────────────┘ │
│                                                          │
│ Univers par défaut   [Dashboard ▾]  ← select parmi inclus │
│                                                          │
│ Prévisualisation rapide :                                │
│ ┌──────────────────────────────────────────┐            │
│ │  [◈] [🏠] [◈] [📅]   thème:dark          │            │
│ │  ↑ nav telle qu'elle apparaîtra           │            │
│ └──────────────────────────────────────────┘            │
│                                                          │
│                   [Annuler]    [Enregistrer]             │
└──────────────────────────────────────────────────────────┘
```

**Prévisualisation rapide :**
- Rendu inline, pas de modale
- Montre la nav icon-strip avec les icônes des univers sélectionnés
- Le fond change selon le thème choisi (via CSS variables appliquées sur l'élément preview uniquement)
- Se met à jour en temps réel quand on modifie thème/univers

**Validation :**
- Nom requis
- Au moins 1 univers sélectionné
- L'univers par défaut doit être dans la liste des univers inclus

**API appelée :**
- Création : `POST /api/profiles`
- Modification : `PUT /api/profiles/{id}`

---

## 6. Onglet 3 — Appareils

### 6.1 Vue liste

```
┌──────────────────────────────────────────────────────────┐
│ Appareils enregistrés                                    │
├──────────────────────────────────────────────────────────┤
│ 📱 iPhone Aurélien   aurélien   il y a 2h   [Complet  ▾] │
│ 🖥 PC Bureau         aurélien   il y a 5min [Complet  ▾] │
│ 📺 Salon Tablet      famille    il y a 1j   [Maison   ▾] │
│ 📱 Mobile Famille    famille    jamais      [Mobile   ▾] │
└──────────────────────────────────────────────────────────┘
```

Chaque ligne :
- Icône déduite du nom (mobile/tablet/pc/tv via détection mots-clés)
- Nom du device
- Utilisateur propriétaire
- Dernière activité (`last_seen` formaté : "il y a Xh", "jamais")
- **Select profil** — dropdown avec tous les profils disponibles + option "Aucun (défaut)"

**Comportement :**
- Le changement de profil dans le dropdown appelle immédiatement `POST /api/devices/{id}/profile`
- Feedback toast "Profil mis à jour"
- Pas de bouton Enregistrer — sauvegarde au changement (comme les toggles dans settings)

**API appelée :**
- Liste devices + profil courant : `GET /api/auth/admin/users` (pour ownership) + `GET /api/auth/devices` → enrichi avec `profile_id` depuis la DB
- Assignation : `POST /api/devices/{device_id}/profile` body `{ profile_id }` (ou `null`)

**Note :** nécessite un endpoint dédié — voir section 8.

---

## 7. Schémas de données consommés

### `GET /api/modules`
```json
[
  { "id": "dashboard", "label": "Tableau de bord", "icon": "Layout_white", "category": "core" },
  { "id": "home",      "label": "Domotique",        "icon": "Home_white",   "category": "maison" }
]
```

### `GET /api/universes`
```json
[
  {
    "id": "uuid",
    "name": "Maison",
    "icon": "🏠",
    "color": "#8870ff",
    "position": 1,
    "modules": ["home", "cameras", "senses"]
  }
]
```

### `GET /api/profiles`
```json
[
  {
    "id": "uuid",
    "name": "Complet",
    "theme": "dark",
    "density": "normal",
    "default_universe_id": "uuid",
    "universe_ids": ["uuid1", "uuid2"]
  }
]
```

### `GET /api/admin/devices` *(endpoint à créer — section 8)*
```json
[
  {
    "id": "uuid",
    "device_name": "iPhone Aurélien",
    "user_display_name": "Aurélien",
    "last_seen": 1748700000,
    "is_active": true,
    "profile_id": "uuid-or-null",
    "profile_name": "Complet"
  }
]
```

---

## 8. Endpoint backend supplémentaire requis

À ajouter dans `web/router_profiles.py` :

### `GET /api/admin/devices`
Retourne tous les devices actifs avec leur profil courant.
Requiert groupe `admin`.

```python
@router.get("/api/admin/devices")
async def admin_list_all_devices(request: Request):
    _require_admin(request)
    conn = _connect()
    rows = conn.execute("""
        SELECT d.id, d.device_name, d.last_seen, d.is_active, d.profile_id,
               u.display_name as user_display_name,
               p.name as profile_name
        FROM devices d
        JOIN users u ON d.user_id = u.id
        LEFT JOIN display_profiles p ON d.profile_id = p.id
        WHERE d.is_active = 1
        ORDER BY d.last_seen DESC NULLS LAST
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

---

## 9. Fichier `web/static/views/profile-editor/index.js`

### Structure du module

```javascript
/* ================================================================
   Vue Profile Editor — Gestion des univers, profils et appareils
   ================================================================ */
import { showToast, setInputBarVisible, getToken } from '/static/core/core.js';

const _CSS = '/static/views/profile-editor/style.css';

// ── State ──────────────────────────────────────────────────────
let _modules   = [];   // ModuleDef[]
let _universes = [];   // Universe[]
let _profiles  = [];   // Profile[]
let _devices   = [];   // DeviceWithProfile[]
let _activeTab = 'universes';

// ── Mount / Unmount ────────────────────────────────────────────
export async function mount(viewport, opts = {}) {
  _ensureCSS();
  setInputBarVisible(false);
  viewport.innerHTML = _renderShell();
  _bindTabs();
  await _loadAll();
  _renderTab(_activeTab);
}

export function unmount() { /* pas de cleanup nécessaire */ }

// ── Data loading ───────────────────────────────────────────────
async function _loadAll() {
  const headers = _authHeaders();
  const [mods, unis, profs, devs] = await Promise.all([
    fetch('/api/modules',        { headers }).then(r => r.json()),
    fetch('/api/universes',      { headers }).then(r => r.json()),
    fetch('/api/profiles',       { headers }).then(r => r.json()),
    fetch('/api/admin/devices',  { headers }).then(r => r.json()).catch(() => []),
  ]);
  _modules   = mods;
  _universes = unis;
  _profiles  = profs;
  _devices   = devs;
}

function _authHeaders() {
  const token = getToken();
  return token ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } : {};
}
```

### Rendu principal

```javascript
function _renderShell() {
  return `
  <div class="pe-wrap">
    <div class="s-tabbar">
      <button class="s-tab active" data-tab="universes">Univers</button>
      <button class="s-tab"        data-tab="profiles">Profils</button>
      <button class="s-tab"        data-tab="devices">Appareils</button>
    </div>
    <div class="s-panels" id="pe-panel"></div>
  </div>`;
}
```

### Onglet Univers — rendu liste

```javascript
function _renderUniverses() {
  const panel = document.getElementById('pe-panel');
  const rows = _universes.map(u => {
    const modLabels = u.modules
      .map(id => _modules.find(m => m.id === id)?.label || id)
      .join(', ');
    const preview = modLabels.length > 45 ? modLabels.slice(0, 45) + '…' : modLabels;
    return `
    <div class="pe-row" data-id="${u.id}">
      <div class="pe-row-dot" style="background:${u.color}"></div>
      <div class="pe-row-body">
        <span class="pe-row-name">${_esc(u.name)}</span>
        <span class="pe-row-meta">${_esc(u.color)} · ${_esc(preview)}</span>
      </div>
      <button class="pe-icon-btn" data-action="edit-universe" data-id="${u.id}" title="Modifier">✎</button>
      <button class="pe-icon-btn danger" data-action="del-universe" data-id="${u.id}" title="Supprimer">🗑</button>
    </div>
    <div class="pe-editor-slot" id="editor-universe-${u.id}"></div>`;
  }).join('');

  panel.innerHTML = `
  <div class="pe-section-head">
    <span class="pe-section-title">Univers</span>
    <button class="pe-add-btn" id="btn-new-universe">+ Nouvel univers</button>
  </div>
  <div id="pe-editor-slot-new-universe"></div>
  <div id="pe-universe-list">${rows}</div>`;

  _bindUniverseEvents();
}
```

### Éditeur d'univers (inline)

```javascript
function _renderUniverseEditor(slot, universe = null) {
  const isNew = !universe;
  const byCategory = _groupByCategory(_modules);

  // Modules déjà sélectionnés
  const selected = universe?.modules || [];

  // HTML du dual-list
  const availableHtml = Object.entries(byCategory).map(([cat, mods]) => {
    const filtered = mods.filter(m => !selected.includes(m.id));
    if (!filtered.length) return '';
    return `
    <div class="pe-cat-label">${_catLabel(cat)}</div>
    ${filtered.map(m => `
      <div class="pe-module-item available" data-module="${m.id}" draggable="false">
        <span class="pe-module-label">${_esc(m.label)}</span>
      </div>`).join('')}`;
  }).join('');

  const selectedHtml = selected.map(id => {
    const m = _modules.find(x => x.id === id);
    return `
    <div class="pe-module-item selected" data-module="${id}" draggable="true">
      <span class="pe-drag-handle">⠿</span>
      <span class="pe-module-label">${_esc(m?.label || id)}</span>
    </div>`;
  }).join('');

  slot.innerHTML = `
  <div class="pe-editor">
    <div class="pe-editor-row">
      <label>Nom</label>
      <input id="pe-u-name" type="text" value="${_esc(universe?.name || '')}" placeholder="Ex: Maison" />
    </div>
    <div class="pe-editor-row pe-editor-row-inline">
      <div>
        <label>Icône</label>
        <input id="pe-u-icon" type="text" value="${_esc(universe?.icon || '◈')}" maxlength="4" style="width:60px;text-align:center" />
      </div>
      <div>
        <label>Couleur</label>
        <div class="pe-color-row">
          <input id="pe-u-color-pick" type="color" value="${universe?.color || '#00c8f0'}" />
          <input id="pe-u-color-hex"  type="text"  value="${universe?.color || '#00c8f0'}" maxlength="7" style="width:80px" />
        </div>
      </div>
    </div>
    <div class="pe-editor-row">
      <label>Modules</label>
      <div class="pe-dual-list">
        <div class="pe-list-col">
          <div class="pe-list-title">Disponibles</div>
          <div class="pe-list-items" id="pe-u-available">${availableHtml}</div>
        </div>
        <div class="pe-list-arrows">
          <button id="pe-u-add-all" title="Tout ajouter">»</button>
          <button id="pe-u-remove-all" title="Tout retirer">«</button>
        </div>
        <div class="pe-list-col">
          <div class="pe-list-title">Sélectionnés <small>(glisser pour réordonner)</small></div>
          <div class="pe-list-items droppable" id="pe-u-selected">${selectedHtml}</div>
        </div>
      </div>
    </div>
    <div class="pe-editor-actions">
      <button class="pe-btn-secondary" id="pe-u-cancel">Annuler</button>
      <button class="pe-btn-primary"   id="pe-u-save">Enregistrer</button>
    </div>
  </div>`;

  _bindUniverseEditorEvents(slot, universe);
}
```

### Onglet Profils — éditeur avec prévisualisation

```javascript
function _renderProfileEditor(slot, profile = null) {
  const isNew = !profile;
  const selectedUniIds = profile?.universe_ids || [];

  const themeOptions = ['dark','light','midnight','graphite']
    .map(t => `<option value="${t}" ${profile?.theme === t ? 'selected' : ''}>${t}</option>`)
    .join('');

  const densityOptions = [
    ['compact','Compact'], ['normal','Normal'], ['comfortable','Confortable']
  ].map(([v,l]) => `<option value="${v}" ${profile?.density === v ? 'selected' : ''}>${l}</option>`)
   .join('');

  const availUnis = _universes.filter(u => !selectedUniIds.includes(u.id));
  const selUnis   = selectedUniIds.map(id => _universes.find(u => u.id === id)).filter(Boolean);

  slot.innerHTML = `
  <div class="pe-editor">
    <div class="pe-editor-row">
      <label>Nom</label>
      <input id="pe-p-name" type="text" value="${_esc(profile?.name || '')}" placeholder="Ex: Mobile" />
    </div>
    <div class="pe-editor-row pe-editor-row-inline">
      <div>
        <label>Thème</label>
        <select id="pe-p-theme">${themeOptions}</select>
      </div>
      <div>
        <label>Densité</label>
        <select id="pe-p-density">${densityOptions}</select>
      </div>
    </div>
    <div class="pe-editor-row">
      <label>Univers</label>
      <div class="pe-dual-list">
        <div class="pe-list-col">
          <div class="pe-list-title">Disponibles</div>
          <div class="pe-list-items" id="pe-p-available">
            ${availUnis.map(u => `
            <div class="pe-universe-item available" data-id="${u.id}">
              <span class="pe-uni-dot" style="background:${u.color}"></span>
              <span>${_esc(u.name)}</span>
            </div>`).join('')}
          </div>
        </div>
        <div class="pe-list-col">
          <div class="pe-list-title">Inclus <small>(glisser pour réordonner)</small></div>
          <div class="pe-list-items droppable" id="pe-p-selected">
            ${selUnis.map(u => `
            <div class="pe-universe-item selected" data-id="${u.id}" draggable="true">
              <span class="pe-drag-handle">⠿</span>
              <span class="pe-uni-dot" style="background:${u.color}"></span>
              <span>${_esc(u.name)}</span>
            </div>`).join('')}
          </div>
        </div>
      </div>
    </div>
    <div class="pe-editor-row">
      <label>Univers par défaut</label>
      <select id="pe-p-default"></select>
    </div>
    <div class="pe-editor-row">
      <label>Prévisualisation</label>
      <div class="pe-preview" id="pe-p-preview"></div>
    </div>
    <div class="pe-editor-actions">
      <button class="pe-btn-secondary" id="pe-p-cancel">Annuler</button>
      <button class="pe-btn-primary"   id="pe-p-save">Enregistrer</button>
    </div>
  </div>`;

  _bindProfileEditorEvents(slot, profile);
  _updateProfilePreview();
}
```

### Prévisualisation temps réel

```javascript
function _updateProfilePreview() {
  const preview = document.getElementById('pe-p-preview');
  if (!preview) return;

  const theme   = document.getElementById('pe-p-theme')?.value || 'dark';
  const selItems = document.querySelectorAll('#pe-p-selected .pe-universe-item');
  const unis    = [...selItems].map(el => {
    const id = el.dataset.id;
    return _universes.find(u => u.id === id);
  }).filter(Boolean);

  // Couleurs de thème (miniature)
  const THEME_COLORS = {
    dark:      { bg: '#07090d', nav: '#0a0e14', accent: '#00c8f0' },
    light:     { bg: '#f0f3f7', nav: '#f7f9fc', accent: '#0099cc' },
    midnight:  { bg: '#000308', nav: '#020810', accent: '#00d8ff' },
    graphite:  { bg: '#1a1a1e', nav: '#141416', accent: '#ff6b35' },
  };
  const c = THEME_COLORS[theme] || THEME_COLORS.dark;

  preview.innerHTML = `
  <div class="pe-preview-shell" style="background:${c.bg};border-radius:8px;overflow:hidden;display:flex;height:64px">
    <div class="pe-preview-nav" style="background:${c.nav};width:36px;display:flex;flex-direction:column;align-items:center;padding:6px 0;gap:4px">
      ${unis.map(u => `
      <div style="width:22px;height:22px;border-radius:6px;background:${u.color}20;
                  border:1px solid ${u.color}60;display:flex;align-items:center;
                  justify-content:center;font-size:10px" title="${_esc(u.name)}">${u.icon}</div>`).join('')}
    </div>
    <div style="flex:1;background:${c.bg};padding:8px">
      <div style="height:8px;background:${c.accent}20;border-radius:4px;margin-bottom:5px"></div>
      <div style="height:6px;background:${c.accent}10;border-radius:4px;width:70%;margin-bottom:4px"></div>
      <div style="height:6px;background:${c.accent}10;border-radius:4px;width:50%"></div>
    </div>
  </div>`;

  // Mettre à jour le select "Univers par défaut"
  const defSel = document.getElementById('pe-p-default');
  if (defSel) {
    const currentVal = defSel.value;
    defSel.innerHTML = unis.map(u =>
      `<option value="${u.id}" ${u.id === currentVal ? 'selected' : ''}>${_esc(u.name)}</option>`
    ).join('') || '<option value="">— aucun —</option>';
  }
}
```

### Onglet Appareils

```javascript
function _renderDevices() {
  const panel = document.getElementById('pe-panel');

  function _deviceIcon(name) {
    const n = name.toLowerCase();
    if (n.includes('phone') || n.includes('iphone') || n.includes('mobile')) return '📱';
    if (n.includes('tablet') || n.includes('ipad'))  return '📱';
    if (n.includes('tv') || n.includes('salon'))     return '📺';
    if (n.includes('mac') || n.includes('pc') || n.includes('bureau') || n.includes('desktop')) return '🖥';
    return '📟';
  }

  function _lastSeen(ts) {
    if (!ts) return 'jamais';
    const diff = Math.floor((Date.now() / 1000) - ts);
    if (diff < 60)    return 'à l\'instant';
    if (diff < 3600)  return `il y a ${Math.floor(diff/60)} min`;
    if (diff < 86400) return `il y a ${Math.floor(diff/3600)} h`;
    return `il y a ${Math.floor(diff/86400)} j`;
  }

  const profileOptions = [
    '<option value="">— défaut (Complet) —</option>',
    ..._profiles.map(p => `<option value="${p.id}">${_esc(p.name)}</option>`),
  ].join('');

  const rows = _devices.map(d => `
  <div class="pe-row">
    <span class="pe-row-icon">${_deviceIcon(d.device_name)}</span>
    <div class="pe-row-body">
      <span class="pe-row-name">${_esc(d.device_name)}</span>
      <span class="pe-row-meta">${_esc(d.user_display_name)} · ${_lastSeen(d.last_seen)}</span>
    </div>
    <select class="pe-profile-select" data-device="${d.id}">
      ${_profiles.map(p => `
        <option value="${p.id}" ${d.profile_id === p.id ? 'selected' : ''}>${_esc(p.name)}</option>
      `).join('')}
      <option value="" ${!d.profile_id ? 'selected' : ''}>— défaut —</option>
    </select>
  </div>`).join('');

  panel.innerHTML = `
  <div class="pe-section-head">
    <span class="pe-section-title">Appareils enregistrés</span>
  </div>
  ${rows || '<p class="pe-empty">Aucun appareil enregistré.</p>'}`;

  // Binding immédiat au changement
  panel.querySelectorAll('.pe-profile-select').forEach(sel => {
    sel.addEventListener('change', async () => {
      const deviceId  = sel.dataset.device;
      const profileId = sel.value || null;
      await _assignProfile(deviceId, profileId);
    });
  });
}

async function _assignProfile(deviceId, profileId) {
  try {
    const r = await fetch(`/api/devices/${deviceId}/profile`, {
      method: 'POST',
      headers: _authHeaders(),
      body: JSON.stringify({ profile_id: profileId }),
    });
    if (!r.ok) throw new Error(await r.text());
    showToast('Profil mis à jour');
    // Mettre à jour le cache local
    const dev = _devices.find(d => d.id === deviceId);
    if (dev) dev.profile_id = profileId;
  } catch (e) {
    showToast('Erreur : ' + e.message);
  }
}
```

### Helpers drag & drop (réutilisable pour modules et univers)

```javascript
function _bindDragDrop(listEl) {
  let dragged = null;

  listEl.addEventListener('dragstart', e => {
    dragged = e.target.closest('[draggable]');
    dragged?.classList.add('dragging');
  });

  listEl.addEventListener('dragend', () => {
    dragged?.classList.remove('dragging');
    dragged = null;
  });

  listEl.addEventListener('dragover', e => {
    e.preventDefault();
    const target = e.target.closest('[draggable]');
    if (target && dragged && target !== dragged) {
      const rect = target.getBoundingClientRect();
      const after = e.clientY > rect.top + rect.height / 2;
      listEl.insertBefore(dragged, after ? target.nextSibling : target);
    }
  });
}
```

---

## 10. Fichier `web/static/views/profile-editor/style.css`

Coller au système de design existant (variables CSS du thème courant).

```css
/* ================================================================
   Profile Editor View
   ================================================================ */

.pe-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Section header ──────────────────────────────────────────── */
.pe-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 10px;
}
.pe-section-title { font-size: 13px; font-weight: 700; opacity: .7; }

.pe-add-btn {
  padding: 5px 12px;
  border-radius: 7px;
  border: 1px solid rgba(255,255,255,.15);
  background: transparent;
  color: var(--accent, #00c8f0);
  font-size: 12px; font-weight: 700;
  cursor: pointer;
  transition: background .15s;
}
.pe-add-btn:hover { background: rgba(255,255,255,.06); }

/* ── List rows ───────────────────────────────────────────────── */
.pe-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 4px;
  border-bottom: 1px solid rgba(255,255,255,.05);
}
.pe-row-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.pe-row-icon { font-size: 16px; flex-shrink: 0; }
.pe-row-body { flex: 1; min-width: 0; }
.pe-row-name { font-size: 13px; font-weight: 700; display: block; }
.pe-row-meta { font-size: 11px; opacity: .5; font-family: 'JetBrains Mono', monospace; }
.pe-icon-btn {
  padding: 4px 8px; border-radius: 6px;
  border: 1px solid rgba(255,255,255,.1);
  background: transparent; color: rgba(255,255,255,.5);
  cursor: pointer; font-size: 13px; flex-shrink: 0;
  transition: all .12s;
}
.pe-icon-btn:hover { color: var(--text, #fff); border-color: rgba(255,255,255,.25); }
.pe-icon-btn.danger:hover { color: var(--red, #ff3659); border-color: var(--red, #ff3659); }

/* ── Inline editor ───────────────────────────────────────────── */
.pe-editor {
  background: rgba(255,255,255,.03);
  border: 1px solid rgba(255,255,255,.1);
  border-radius: 10px;
  padding: 16px;
  margin: 4px 0 10px;
  display: flex; flex-direction: column; gap: 14px;
}
.pe-editor-row label {
  display: block; font-size: 11px; font-weight: 700;
  opacity: .55; text-transform: uppercase; letter-spacing: .08em;
  margin-bottom: 5px;
}
.pe-editor-row input[type="text"],
.pe-editor-row select {
  width: 100%;
  background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 7px;
  color: var(--text, #fff);
  font-size: 13px;
  padding: 7px 10px;
  outline: none;
  transition: border-color .15s;
}
.pe-editor-row input:focus,
.pe-editor-row select:focus { border-color: var(--accent, #00c8f0); }

.pe-editor-row-inline { display: flex; gap: 16px; }
.pe-editor-row-inline > div { flex: 1; }

.pe-color-row { display: flex; align-items: center; gap: 8px; }
.pe-color-row input[type="color"] {
  width: 32px; height: 32px; border-radius: 6px;
  border: 1px solid rgba(255,255,255,.15);
  padding: 2px; cursor: pointer; background: transparent;
}

/* ── Dual list ───────────────────────────────────────────────── */
.pe-dual-list {
  display: flex; gap: 10px; align-items: flex-start;
}
.pe-list-col { flex: 1; }
.pe-list-title {
  font-size: 10px; font-weight: 700; opacity: .5;
  text-transform: uppercase; letter-spacing: .08em;
  margin-bottom: 6px;
}
.pe-list-title small { font-size: 9px; opacity: .7; }
.pe-list-items {
  min-height: 80px; max-height: 200px; overflow-y: auto;
  border: 1px solid rgba(255,255,255,.1); border-radius: 8px;
  padding: 4px;
}
.pe-list-items.droppable { border-color: rgba(255,255,255,.18); }
.pe-list-arrows {
  display: flex; flex-direction: column; gap: 6px;
  justify-content: center; padding-top: 24px;
}
.pe-list-arrows button {
  padding: 3px 6px; border-radius: 5px;
  border: 1px solid rgba(255,255,255,.15);
  background: transparent; color: rgba(255,255,255,.5);
  cursor: pointer; font-size: 13px;
}
.pe-list-arrows button:hover { color: var(--text, #fff); }

/* ── Module items ────────────────────────────────────────────── */
.pe-cat-label {
  font-size: 9px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .1em; opacity: .4; padding: 4px 6px 2px;
}
.pe-module-item, .pe-universe-item {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 8px; border-radius: 6px;
  font-size: 12px; cursor: pointer;
  transition: background .12s;
  user-select: none;
}
.pe-module-item:hover, .pe-universe-item:hover {
  background: rgba(255,255,255,.07);
}
.pe-module-item.dragging, .pe-universe-item.dragging {
  opacity: .4; background: rgba(255,255,255,.04);
}
.pe-drag-handle { opacity: .35; font-size: 14px; cursor: grab; }
.pe-uni-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.pe-module-label { flex: 1; }

/* ── Actions ─────────────────────────────────────────────────── */
.pe-editor-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  padding-top: 4px; border-top: 1px solid rgba(255,255,255,.06);
}
.pe-btn-primary, .pe-btn-secondary {
  padding: 7px 16px; border-radius: 8px;
  font-size: 12px; font-weight: 700; cursor: pointer;
  transition: all .15s;
}
.pe-btn-primary {
  background: var(--accent, #00c8f0); color: #000; border: none;
}
.pe-btn-primary:hover { filter: brightness(1.1); }
.pe-btn-secondary {
  background: transparent; border: 1px solid rgba(255,255,255,.15);
  color: rgba(255,255,255,.6);
}
.pe-btn-secondary:hover { border-color: rgba(255,255,255,.3); color: var(--text, #fff); }

/* ── Profile select (devices tab) ────────────────────────────── */
.pe-profile-select {
  padding: 5px 8px; border-radius: 7px;
  border: 1px solid rgba(255,255,255,.12);
  background: rgba(255,255,255,.05); color: var(--text, #fff);
  font-size: 11px; cursor: pointer;
}

/* ── Preview ─────────────────────────────────────────────────── */
.pe-preview { margin-top: 2px; }

/* ── Empty state ─────────────────────────────────────────────── */
.pe-empty { color: rgba(255,255,255,.35); font-size: 12px; padding: 16px 0; }
```

---

## 11. Ordre d'implémentation

1. **Backend d'abord** (spec `ADA_SPEC_PROFILES_UNIVERSES.md`, sections 3→8)
2. Ajouter `GET /api/admin/devices` (section 8 de cette spec)
3. Ajouter `"profile-editor"` dans `PERMISSION_GROUPS["admin"]` dans `auth_permissions.py`
4. Créer `web/static/views/profile-editor/style.css` (section 10)
5. Créer `web/static/views/profile-editor/index.js` (sections 4→9)
6. Modifier `web/static/core/core.js` — ajouter dans `VIEW_LOADERS` et `VIEW_TITLES`
7. Modifier `web/static/index.html` — ajouter l'entrée nav
8. Tester : créer un univers, créer un profil, assigner à un device, vérifier que `/api/profile` retourne le bon profil

---

## 12. Règles à respecter

- **CSS isolation** : toutes les classes prefixées `pe-` pour éviter les conflits
- **Pas de framework** : vanilla JS uniquement (comme le reste de l'app)
- **Pas de modale** : tout s'ouvre inline (pattern accordion)
- **Pas de sauvegarde auto** : sauf pour l'assignation device → profil (save on change)
- **Cohérence visuelle** : utiliser les variables CSS du thème (`var(--accent)`, `var(--text)`, etc.)
- **Accessibilité** : labels sur tous les inputs, boutons avec `title`
- **Sécurité** : escape systématique des données affichées via `_esc()` (déjà disponible dans `core.js` comme `escapeHtml`)
