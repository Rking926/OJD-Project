# OJD — Assistant OSINT

Application d'investigation OSINT pilotable par prompt texte ou voix, avec
des modules d'outils (Sherlock, WHOIS, Toutatis...) ajoutables sans toucher
au cœur de l'app.

## Démarrer le MVP

```bash
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

Puis ouvrir http://localhost:8000 dans Chrome (la reconnaissance vocale
utilise l'API Web Speech, disponible nativement dans Chrome).

## Premiers pas

1. Ouvrir ⚙️ **Paramètres** et renseigner une clé API Anthropic (ou passer
   sur Ollama si un modèle local tourne sur la machine).
2. Créer une **nouvelle enquête** : un titre + un **motif de recherche**
   obligatoire (traçabilité / RGPD).
3. Taper un prompt, ex: *"cherche le pseudo johndoe42 sur les réseaux
   sociaux"*, ou cliquer sur 🎤 pour dicter.
4. L'assistant choisit les modules à appeler (ici `sherlock`), les exécute
   réellement, et les résultats (profils, emails, domaines...) apparaissent
   à droite comme entités, avec le graphe de relations et le journal
   d'audit complet.

## Architecture

```
backend/
  app/
    models.py            # entités, relations, investigations, audit (SQLite)
    config_store.py       # paramètres locaux (clé API, config modules)
    modules/
      base.py             # interface OsintModule — contrat pour tout nouveau module
      sherlock_module.py  # recherche de pseudo (fonctionnel)
      whois_module.py     # whois domaine (fonctionnel)
      toutatis_module.py  # infos Instagram (nécessite sessionid, hors CGU — désactivé par défaut)
      registry.py         # liste des modules actifs
    orchestrator/
      providers.py        # abstraction LLM : AnthropicProvider / OllamaProvider
      orchestrator.py      # boucle prompt -> tool use -> exécution modules -> synthèse
    main.py               # API FastAPI + sert le frontend statique
frontend/
  index.html / app.js     # UI vanilla JS : chat, micro (Web Speech API), entités, graphe SVG
```

## Ajouter un nouveau module OSINT

1. Créer `backend/app/modules/mon_outil_module.py`, hériter de `OsintModule`
   (voir `base.py`), implémenter `run(input_type, value, config)`.
2. L'ajouter dans `registry.py`.
3. Le LLM le découvre automatiquement comme outil disponible — rien d'autre
   à modifier.

## Roadmap (pas encore fait)

- Migration vers une app desktop packagée (Tauri) pour la distribution
  commerciale, au lieu du navigateur.
- Carte 3D des lieux liés aux entités (panneau additionnel, ex: CesiumJS/MapLibre).
- STT local (faster-whisper) en remplacement/complément du Web Speech API,
  pour un fonctionnement 100% hors-ligne.
- Stockage chiffré des secrets (clé API, sessionid) via le trousseau du système.
- Système de licences/permissions par module pour la revente à des tiers
  (cadre CNAPS / RGPD à valider avant commercialisation).

## ⚠️ Cadre légal

Cette app n'interroge que des sources librement accessibles ou fournies
par l'utilisateur lui-même (ex: sessionid Instagram personnel pour
`toutatis`). Chaque enquête exige un motif de recherche conservé dans le
journal d'audit. Avant toute distribution commerciale à des agents de
sécurité privée, valider le cadre RGPD et CNAPS applicable.
