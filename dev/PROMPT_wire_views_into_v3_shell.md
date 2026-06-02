# PROMPT — Câblage de toutes les vues dans le shell ada-v3

## Contexte du projet

- **Stack** : Python 3.11 · FastAPI · SQLite · Vanilla JS (non-module dans le shell)
- **Shell actuel** : `web/static/index.html` — design ada-v3, grid CSS (topbar 44px · nav 52px · content · chat 300px)
- **Vues existantes** : modules ES dans `web/static/views/{nom}/index.js`, chacun exporte `async function mount(container, opts?)`
- **Authentification** : JWT dans `localStorage['ada_token']`. Le shell expose `_getToken()`.

## Fichiers déjà créés / modifiés

| Fichier | État |
|---|---|
| `web/static/index.html` | Shell ada-v3 complet — nav univers, chat SSE, auth overlay, admin menu |
| `web/static/core/core.js` | Patché avec `?.` optional chaining sur tous les éléments DOM de l'ancien shell |
| `web/static/views/profile-editor/index.js` | Vue admin 3-onglets — chargée via `openView('profile-editor')` |
| `web/static/views/settings/index.js` | Vue paramètres 5-onglets — chargée via `openView('settings')` |

## Structure du shell ada-v3 (index.html)

### Univers et sous-panneaux actuels

```
#uni-dash        → Dashboard (contenu statique mock)
#uni-home
  #sub-domo      → Domotique (contenu statique mock)
  #sub-cameras   → Caméras (contenu statique mock)
  #sub-membres   → Membres (vide)
  #sub-courses   → Courses (vide)
#uni-co
  #sub-infra     → Infrastructure (contenu statique mock)
  #sub-rmm       → RMM Clients (contenu statique mock)
  #sub-tel       → Téléphonie (vide)
  #sub-mkt       → Marketing (contenu statique mock)
#uni-plan
  #sub-briefing  → Briefing (contenu statique mock)
  #sub-agenda    → Agenda (contenu statique mock)
#uni-tools
  #sub-skills    → Compétences (contenu statique mock)
  #sub-mem       → Mémoire (vide — "à charger")
  #sub-settings  → Paramètres (vide — "à charger")
```

### Fonctions JS clés dans le shell

```js
// Navigation
goUni(id, btn)         // active un univers
goSub(el, subId)       // active un sous-onglet

// Vue overlay (modal plein écran)
openView(name)         // charge dynamiquement /static/views/{name}/index.js dans #view-body
closeView()

// Nav latérale expandable
toggleNav()            // bascule nav 52px ↔ 180px

// Admin (topbar droite)
adminRestart()         // POST /api/admin/restart
adminClearCache()      // vide SW cache
adminLogout()          // efface token + reload

// Chat
sendMsg()              // SSE vers /api/chat
inject(text)           // pré-remplit l'input chat
```

## Travail demandé

### 1. Mécanisme de chargement lazy des vues

Dans `web/static/index.html`, ajouter une fonction `_loadSubView(subId, viewName, opts={})` :

```js
// Lazy-mount d'une vue ES module dans un sous-panneau
// - N'importe qu'une seule fois (data-loaded="1" sur le container)
// - Affiche un spinner pendant le chargement
// - Monte la vue dans le div #subId
async function _loadSubView(subId, viewName, opts={}) {
  const el = document.getElementById(subId);
  if (!el || el.dataset.loaded) return;
  el.dataset.loaded = '1';
  el.innerHTML = '<p style="padding:24px;color:var(--text-dim);font-size:12px">Chargement…</p>';
  try {
    const { mount } = await import(`/static/views/${viewName}/index.js`);
    el.innerHTML = '';
    await mount(el, { token: _getToken(), ...opts });
  } catch(e) {
    el.innerHTML = `<p style="padding:24px;color:var(--text-dim);font-size:12px">Erreur : ${e.message}</p>`;
    el.dataset.loaded = '';  // permet de réessayer
    console.error('_loadSubView', viewName, e);
  }
}
```

### 2. Modifier `goUni()` — chargement au premier accès à un univers

Dans `goUni(id, btn)`, ajouter après l'affichage du panel :

```js
// Charger le dashboard réel au premier accès
if (id === 'dash') _loadSubView('uni-dash-content', 'dashboard');
// Charger la vue société au premier accès à "co"
if (id === 'co')   _loadSubView('sub-infra', 'societe');
```

Note : le `#uni-dash` est un panel direct sans sous-onglets. Son contenu doit être dans un `<div id="uni-dash-content">` — il faut encapsuler le contenu statique existant dans ce div.

### 3. Modifier `goSub()` — lazy-load par sous-panneau

Après l'activation du sous-panneau, ajouter un `switch` :

```js
// Mapping sous-panneau → vue à charger
const VIEW_MAP = {
  'sub-cameras':  ['cameras',   {}],
  'sub-mkt':      ['marketing', {}],
  'sub-mem':      ['memory',    {}],
  'sub-briefing': ['briefing',  {}],
  'sub-agenda':   ['planner',   {}],
  // 'sub-domo' et 'sub-infra' → vue 'page' avec contexte
  'sub-domo':     ['page',      { page: 'home',           hint: 'État domotique complet' }],
  'sub-infra':    ['page',      { page: 'infrastructure', hint: 'État infrastructure' }],
  'sub-rmm':      ['page',      { page: 'printers',       hint: 'RMM clients actifs' }],
};
if (VIEW_MAP[subId]) {
  const [vName, opts] = VIEW_MAP[subId];
  _loadSubView(subId, vName, opts);
}
// Paramètres → overlay
if (subId === 'sub-settings') { openView('settings'); }
```

### 4. Vue Société (`#uni-co`)

La vue `societe` est une vue complète autonome. Elle doit :
- Être montée dans le panel entier `#uni-co` au premier accès
- Remplacer **tous** les sous-onglets statiques (sub-infra, sub-rmm, sub-tel, sub-mkt) car elle gère sa propre navigation interne
- Le HTML du `#uni-co` doit être simplifié : supprimer la `subtab-bar` statique, laisser juste un div container vide pour que `societe/index.js` monte dedans

```html
<!-- #uni-co simplifié -->
<div class="uni-panel" id="uni-co">
  <!-- societe view monte ici au premier goUni('co') -->
</div>
```

Et dans `goUni` :
```js
if (id === 'co') _loadSubView('uni-co', 'societe');
```

Note : `societe/index.js` import `core.js` — déjà patché ✓

### 5. Intercepter `switchView()` appelé depuis les vues

Certaines vues (ex: `dashboard/index.js`) appellent :
```js
import('/static/core/core.js').then(({ switchView }) => switchView('planner'));
```

Dans le nouveau shell, `switchView` de `core.js` ne fonctionnera pas (pas de `#viewport`). 

**Solution** : exposer une fonction globale `window.adaNavigate(viewName)` qui fait la correspondance :

```js
// Dans index.html, dans le bloc <script>
const _VIEW_TO_UNI = {
  'dashboard': 'dash',
  'cameras':   ['home', 'sub-cameras'],
  'marketing': ['co',   'sub-mkt'],
  'briefing':  ['plan', 'sub-briefing'],
  'planner':   ['plan', 'sub-agenda'],
  'memory':    ['tools','sub-mem'],
  'settings':  null,   // → openView()
  'societe':   'co',
  'webagent':  null,   // → openView('webagent') si ça existe
};
window.adaNavigate = function(viewName) {
  const target = _VIEW_TO_UNI[viewName];
  if (!target) { openView(viewName); return; }
  if (Array.isArray(target)) {
    const [uni, sub] = target;
    const uniBtn = document.querySelector(`[data-uni="${uni}"]`);
    if (uniBtn) goUni(uni, uniBtn);
    setTimeout(() => {
      const stabEl = document.querySelector(`[onclick*="${sub}"]`);
      if (stabEl) goSub(stabEl, sub);
    }, 50);
  } else {
    const uniBtn = document.querySelector(`[data-uni="${target}"]`);
    if (uniBtn) goUni(target, uniBtn);
  }
};
```

Et patcher `core.js` pour que `switchView` appelle `window.adaNavigate` si disponible :
```js
// Dans core.js — début de switchView()
export async function switchView(viewName, opts = {}) {
  if (window.adaNavigate) { window.adaNavigate(viewName); return; }
  // ... reste du code existant
```

### 6. Dashboard réel (`#uni-dash`)

Le dashboard statique contient des KPIs hardcodés. La vue `dashboard/index.js` monte un vrai tableau de bord avec données live depuis `/api/dashboard`.

Actions :
1. Remplacer le contenu statique de `#uni-dash` par un div vide `<div id="uni-dash-content"></div>`  
2. Au chargement initial du shell (dans l'IIFE d'auth), appeler `_loadSubView('uni-dash-content', 'dashboard')` directement.

### 7. Vue Briefing réelle (`#sub-briefing`)

La vue `briefing/index.js` charge le briefing du jour depuis l'API. Elle remplace le contenu mock.

Actions : le `goSub` vers `sub-briefing` déclenchera `_loadSubView('sub-briefing', 'briefing')`.

Le bouton "⚡ Regénérer" statique doit être supprimé du HTML — la vue gère ses propres boutons.

### 8. Paramètres via overlay (sub-settings)

Le stab "Paramètres" dans `uni-tools` appelle déjà `goSub(this,'sub-settings')`.  
Dans le `VIEW_MAP` de `goSub`, le mapping `'sub-settings' → openView('settings')` est suffisant.  
Le `div#sub-settings` peut rester vide (le contenu s'affiche dans l'overlay).

### 9. Onglet "Paramètres" dans `uni-tools` — Retirer ou pointer vers overlay

Simplifier : renommer le stab en "⚙ Config" et au clic appeler directement `openView('settings')` au lieu de `goSub(this,'sub-settings')`.

Même chose pour un éventuel stab "Profils" → `openView('profile-editor')`.

### 10. Injection du contexte actif dans le chat

La variable `_activeSub` doit être exposée pour enrichir les messages. Dans `sendMsg()`, le `company_context` envoyé à `/api/chat` doit inclure l'univers actif et le sous-panneau actif.

Ajouter dans le script :
```js
let _activeUni = 'dash';
let _activeSub = '';
// Mettre à jour dans goUni et goSub
```

Et dans `sendMsg()`, ajouter dans le body JSON :
```js
context: `Univers actif: ${_activeUni}${_activeSub ? ' › ' + _activeSub : ''}`
```

## Contraintes

- **Ne jamais casser l'auth** — si `_getToken()` retourne null après `_checkAuth()`, ne pas charger les vues, attendre `_onAuthenticated()`.
- **Guard MODULE_SOCIETE** — si le module societe n'est pas disponible, `_loadSubView` doit attraper l'erreur 404 silencieusement.  
- **Performance** — chaque vue n'est chargée qu'une seule fois (flag `data-loaded`). Ne pas recharger si déjà monté.
- **core.js déjà patché** — le `?.` optional chaining est en place. Ne pas re-patcher core.js sauf pour `switchView`.
- **Tests existants** — `venv/bin/python -m pytest tests/test_profiles.py -v` doit rester à 16/16 ✓.

## Fichiers à modifier

1. **`web/static/index.html`** — c'est le seul fichier principal à modifier :
   - Ajouter `_loadSubView()`
   - Modifier `goUni()` — trigger dashboard + societe
   - Modifier `goSub()` — VIEW_MAP lazy loading
   - Ajouter `window.adaNavigate()`
   - Simplifier HTML `#uni-dash` (div content vide)
   - Simplifier HTML `#uni-co` (vider pour societe)
   - Mettre à jour stab paramètres → `openView('settings')`
   - Ajouter `_activeUni` / `_activeSub` tracking

2. **`web/static/core/core.js`** — un seul ajout au début de `switchView()` :
   ```js
   if (window.adaNavigate) { window.adaNavigate(viewName); return; }
   ```

## Ordre d'implémentation recommandé

1. Patcher `switchView` dans `core.js` (2 lignes)
2. Ajouter `_loadSubView` + `window.adaNavigate` dans index.html
3. Modifier `goUni` (hooks dashboard + societe)
4. Modifier `goSub` (VIEW_MAP)
5. Simplifier HTML `#uni-dash` + `#uni-co`
6. Appel `_loadSubView('uni-dash-content','dashboard')` dans `_onAuthenticated()`
7. Tester visuellement chaque univers
8. Vérifier `pytest tests/test_profiles.py` — 16/16 ✓
