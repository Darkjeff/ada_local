---
id: seed_domain_margep
name: MargePro — Gestion des marges et pricing
domain: margep
priority: 2
summary: Calcul des marges, pricing, seuils de rentabilité pour MargePro
---
## MargePro — Module de gestion des marges

Contexte de calcul financier et de pricing pour les devis et contrats.

## Indicateurs clés

- **Marge brute** = (Prix vente HT - Coût achat HT) / Prix vente HT × 100
- **Taux horaire** : varie selon le type de prestation et le profil
- **Seuil de rentabilité** : à calculer par projet

## Règles de pricing

- Prestations de conseil : marge cible ≥ 40%
- Fournitures et équipements : marge cible ≥ 20%
- Maintenance récurrente : marge cible ≥ 50%
- Projets au forfait : prévoir 15% de réserve risque

## Alertes automatiques

- Marge < 20% → alerte rouge dans le tableau de bord
- Marge 20-30% → alerte orange
- Marge > 30% → indicateur vert

## Formules utiles

```
Prix vente = Coût / (1 - taux_marge)
Marge brute = Prix vente - Coût achat
Taux marge = Marge brute / Prix vente
Taux marque = Marge brute / Coût achat
```
