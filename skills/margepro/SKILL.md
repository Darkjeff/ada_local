---
name: margepro
description: Contexte produit MargePro — agent marketing et copywriting
triggers:
  - margepro
  - marge pro
  - post linkedin
  - post twitter
  - post instagram
  - accroche
  - hook
  - copywriting
  - contenu marketing
  - stratégie contenu
  - bio profil
  - objection client
  - séquence email
  - email de prospection
---
# MargePro — Agent Social Media : Guide de Setup
> Version : 12.66.3  
> Statut : Guide opérationnel — format obligatoire markdown  
> Objet : Installation et configuration de l'agent de publication social media  
> Stack : Ollama + n8n + Meta Business (Facebook + Instagram)  
> Date : mai 2026

---

## 1. Vue d'ensemble de la stack

```
Ollama (local Windows)
    modèle LLM en local — génère les posts par segment métier
        ↓
n8n (local Windows)
    orchestration — planifie, adapte, publie
        ↓
Meta Business API
    Facebook Page MargePro + Instagram Business
        ↓
Publication automatique
    posts planifiés par réseau et par segment

+ action humaine
    copie-colle dans groupes Facebook ciblés (VTC, artisans, etc.)
```

---

## 2. Prérequis matériel

| Composant | Minimum | Recommandé |
|---|---|---|
| RAM | 8 Go | 16 Go |
| Stockage libre | 5 Go | 10 Go |
| OS | Windows 10 64-bit | Windows 11 64-bit |
| Connexion | Internet | Internet |

---

## 3. Étape 1 — Installer Ollama sur Windows

### 3.1 Téléchargement

```
https://ollama.com/download/windows
```

Télécharger et lancer l'installeur `.exe`. Ollama s'installe comme un service Windows.

### 3.2 Vérification

Ouvrir un terminal PowerShell :

```powershell
ollama --version
```

### 3.3 Choisir et télécharger un modèle

Selon la RAM disponible :

```powershell
# 8 Go RAM — modèle léger, bon français
ollama pull mistral

# 16 Go RAM ou plus — meilleure qualité
ollama pull llama3

# Alternatif léger et performant
ollama pull gemma3
```

Le téléchargement prend 5 à 15 minutes selon la connexion.

### 3.4 Tester le modèle

```powershell
ollama run mistral "Écris un post Facebook pour un plombier auto-entrepreneur qui veut savoir si son intervention d'urgence est rentable."
```

Si une réponse cohérente s'affiche, Ollama fonctionne.

### 3.5 Lancer Ollama en mode serveur local

```powershell
ollama serve
```

Ollama écoute sur `http://localhost:11434`. Laisser ce terminal ouvert (ou configurer le service Windows pour démarrer automatiquement).

---

## 4. Étape 2 — Installer n8n sur Windows

### 4.1 Prérequis : Node.js

Télécharger et installer Node.js LTS :

```
https://nodejs.org/fr/download
```

Vérification :

```powershell
node --version
npm --version
```

### 4.2 Installer n8n

```powershell
npm install -g n8n
```

### 4.3 Lancer n8n

```powershell
n8n start
```

n8n démarre sur `http://localhost:5678`.

Ouvrir le navigateur sur cette adresse. Créer un compte local (email + mot de passe, stocké localement).

### 4.4 Démarrage automatique (optionnel)

Pour que n8n démarre avec Windows, créer un script `.bat` dans le dossier de démarrage Windows :

```bat
@echo off
start "" "ollama serve"
timeout /t 5
start "" "n8n start"
```

---

## 5. Étape 3 — Créer les comptes Meta Business

### 5.1 Compte Facebook personnel

Si pas encore de compte Facebook personnel :
```
https://www.facebook.com
```
Créer un compte avec ton email professionnel.

### 5.2 Créer une Page Facebook MargePro

1. Sur Facebook, cliquer **"Créer"** → **"Page"**
2. Nom de la page : `MargePro`
3. Catégorie : `Logiciel` ou `Application mobile`
4. Ajouter une description courte :
   > *Calculez votre vraie marge avant de dire oui. Pour artisans et auto-entrepreneurs.*
5. Ajouter le logo MargePro et une photo de couverture

### 5.3 Connecter Instagram Business

1. Aller dans les **Paramètres** de la page Facebook
2. Section **Instagram** → **Connecter un compte Instagram**
3. Si pas encore de compte Instagram :
   - Créer `@margepro_officiel` (ou similaire)
   - Le passer en **compte professionnel** dans les réglages Instagram
4. Relier le compte Instagram à la page Facebook

### 5.4 Créer le compte Meta for Developers

```
https://developers.facebook.com
```

1. Se connecter avec le compte Facebook
2. Accepter les conditions développeur
3. Cliquer **"Créer une application"**
4. Type : **Business**
5. Nom : `MargePro Social Agent`
6. Email de contact : ton email

### 5.5 Configurer l'application Meta

Dans le tableau de bord de l'application :

1. Ajouter le produit **"Facebook Login"**
2. Ajouter le produit **"Instagram Graph API"**
3. Dans **Paramètres → De base** :
   - Noter l'`App ID`
   - Noter l'`App Secret`

### 5.6 Générer un token d'accès de page

1. Aller dans **Outils → Explorateur d'API Graph**
2. Sélectionner ton application
3. Cliquer **"Générer un token d'accès utilisateur"**
4. Cocher les permissions :
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_content_publish`
5. Cliquer **"Générer le token"**
6. Copier et conserver ce token (il sera entré dans n8n)

> ⚠️ Le token utilisateur expire après 1 heure. Il faut l'échanger contre un **token de page longue durée** (valable 60 jours). Procédure dans la documentation Meta : [Tokens de longue durée](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived).

---

## 6. Étape 4 — Connecter n8n à Ollama et Meta

### 6.1 Connexion Ollama dans n8n

Dans n8n :

1. **Credentials** → **New Credential**
2. Chercher **"Ollama"**
3. URL de base : `http://localhost:11434`
4. Sauvegarder

### 6.2 Connexion Facebook dans n8n

1. **Credentials** → **New Credential**
2. Chercher **"Facebook Graph API"**
3. Coller le token de page longue durée
4. Sauvegarder

---

## 7. Étape 5 — Premier workflow : post Facebook automatique

### 7.1 Structure du workflow

```
Trigger (planification)
    → Node Ollama (génération du post)
    → Node Facebook (publication)
```

### 7.2 Créer le workflow dans n8n

**Trigger : Schedule**
- Type : Cron
- Exemple : tous les jours à 8h → `0 8 * * *`

**Node : Ollama Chat Model**
- Credential : Ollama (configuré plus haut)
- Modèle : `mistral` (ou `llama3`)
- Prompt système :

```
Tu es un assistant marketing pour MargePro, une application de calcul de marge pour artisans et auto-entrepreneurs français.
Tu génères des posts courts pour Facebook, percutants, en français, sans jargon technique.
Chaque post doit parler d'un problème concret d'un artisan (marge, déplacement, coût caché, SAV, client régulier).
Maximum 3 phrases. Terminer par une question ou un appel à l'action simple.
```

- Prompt utilisateur (exemple segment BTP) :

```
Génère un post Facebook pour un électricien auto-entrepreneur.
Le sujet : vérifier si une petite intervention d'urgence est vraiment rentable une fois le déplacement compté.
Ton : direct, terrain, pas commercial.
```

**Node : Facebook Graph API**
- Méthode : POST
- URL : `https://graph.facebook.com/v19.0/{PAGE_ID}/feed`
- Body :
```json
{
  "message": "{{ $json.response }}",
  "access_token": "{TOKEN}"
}
```

### 7.3 Tester le workflow

Cliquer **"Execute Workflow"** en mode test. Vérifier que le post apparaît sur la page Facebook.

---

## 8. Segments et prompts par métier

Adapter le prompt utilisateur selon le segment cible :

### BTP (plombier, électricien, maçon)

```
Génère un post Facebook pour un [métier] auto-entrepreneur.
Sujet : [déplacement urgent / petit chantier / SAV non facturé / matériaux imprévus].
Ton : direct, terrain, honnête.
```

### Mobilité / VTC / Taxi

```
Génère un post Facebook pour un chauffeur VTC ou taxi indépendant.
Sujet : [coût réel du kilomètre électrique / zone peu rentable / conventionné vs pro].
Ton : communautaire, entre pairs.
```

### Soins à domicile / Coiffure / Esthétique

```
Génère un post Instagram pour une coiffeuse à domicile auto-entrepreneuse.
Sujet : [cliente régulière rentable ou pas / produits qui coûtent plus / trajet non compté].
Ton : bienveillant, pratique, entre professionnelles.
```

### Paysagiste

```
Génère un post Facebook pour un paysagiste auto-entrepreneur.
Sujet : [entretien récurrent / saisonnalité / matériel amorti].
Ton : direct, terrain.
```

---

## 9. Workflow semi-automatique : groupes communautaires

Les groupes Facebook privés (VTC, artisans BTP, taxi, auto-entrepreneurs) **ne peuvent pas recevoir de publications automatiques via API**. La procédure est semi-automatique :

```
n8n génère le post (Ollama)
    ↓
Envoi par email ou Telegram à la personne responsable
    ↓
La personne valide en 1 clic
    ↓
Elle copie-colle dans le groupe Facebook ciblé
```

### Groupes Facebook prioritaires à identifier et rejoindre

- Groupes VTC / Chauffeurs VTC France
- Groupes Taxi indépendants
- Groupes Auto-entrepreneurs BTP
- Groupes Artisans (plombiers, électriciens, maçons)
- Groupes Coiffure à domicile / Esthétique à domicile
- Chambres des métiers locales (pages et groupes)
- Syndicats taxi (contact terrain déjà identifié dans la roadmap)

---

## 10. Calendrier éditorial recommandé

| Jour | Réseau | Segment | Type de post |
|---|---|---|---|
| Lundi | Facebook | BTP | Problème marge (déplacement, SAV) |
| Mardi | Instagram | Soins à domicile | Astuce rentabilité cliente régulière |
| Mercredi | Facebook | VTC / Taxi | Coût réel du kilomètre |
| Jeudi | Instagram | Coiffure / Esthétique | Produits + temps = vraie marge |
| Vendredi | Facebook | Paysagiste / Espaces verts | Saisonnalité et entretien |
| Samedi | Facebook (groupes) | Tous segments | Post communautaire — question ouverte |

---

## 11. Surveillance et itération

### Ce que tu surveilles chaque semaine

- Nombre de likes / partages par post
- Commentaires (signal d'engagement communauté)
- Clics vers margepro.fr (ajouter UTM aux liens)
- Posts qui performent → dupliquer le format

### Amélioration des prompts

Si un post ne convainc pas, affiner le prompt Ollama :
- Ajouter un exemple de bon post
- Préciser le ton
- Réduire ou augmenter la longueur

---

## 12. Évolutions futures

| Phase | Action |
|---|---|
| v2 | Ajout LinkedIn (posts CEO / crédibilité partenaires) |
| v2 | Monitoring automatique des commentaires — réponses semi-auto |
| v3 | TikTok — si ambassadeur terrain identifié (livreurs vélo) |
| v3 | Intégration Orkestri — posts générés depuis les données d'usage réel |

---

## 13. Ressources

- Ollama : https://ollama.com
- n8n : https://n8n.io
- Meta for Developers : https://developers.facebook.com
- Graph API Explorer : https://developers.facebook.com/tools/explorer
- Tokens longue durée Meta : https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived
