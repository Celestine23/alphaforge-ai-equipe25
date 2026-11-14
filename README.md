# AlphaForge AI — Vivez votre placement avant de le faire

**Datathon PolyFinances 2026 · Banque Nationale × AWS**
Simulation uniquement : personas fictifs, aucune transaction, aucun conseil financier personnalisé.

L'assistant fait **vivre** à l'investisseur ce que son placement lui aurait fait traverser (relecture des données 2021-2026, en CAD), **conteste** quand le placement ne respecte pas son contrat d'investisseur, et **prouve** chaque chiffre avec un reçu numéroté (#R-001…) contrôlé par un Vérificateur.

## Architecture

| Composant | Type | Fichier | Service AWS |
| --- | --- | --- | --- |
| Intervieweur | Agent IA (Strands) | `alphaforge/agents.py` | Amazon Bedrock |
| Machine à remonter le temps | Code Python, sans IA | `alphaforge/machine.py` | AWS Lambda (`lambda_function.py`), données dans S3 |
| Règles du contrat (verdict) | Code Python, sans IA | `alphaforge/verdict.py`, `contrats.json` | AWS Lambda |
| Avocat du diable | Agent IA (Strands) | `alphaforge/agents.py` | Amazon Bedrock |
| Explicateur (carte de vérité) | Agent IA (Strands) | `alphaforge/agents.py` | Amazon Bedrock |
| Vérificateur de reçus | Code Python, sans IA | `alphaforge/verificateur.py` | — |
| Traces d'exécution | JSON | `traces/` | Amazon S3, CloudWatch (journaux Lambda) |
| Interface | Streamlit | `app.py` | EC2 (facultatif) |

Principe : **le code calcule et décide ; l'IA questionne, conteste et explique ; le Vérificateur contrôle que chaque chiffre du texte correspond à un reçu.**

## Démarrage rapide (sans AWS, pour tester)

```bash
python -m pip install -r requirements.txt
# Windows PowerShell
$env:ALPHAFORGE_HORS_LIGNE="1"; python scripts/test_rapide.py
$env:ALPHAFORGE_HORS_LIGNE="1"; streamlit run app.py
# Mac / Linux
ALPHAFORGE_HORS_LIGNE=1 python scripts/test_rapide.py
ALPHAFORGE_HORS_LIGNE=1 streamlit run app.py
```

## Avec AWS (Bedrock, Lambda, S3)

1. Identifiants du compte d'équipe : page Workshop Studio → **Get AWS CLI credentials** → copier les variables dans le terminal (elles expirent : les recopier si une erreur `ExpiredToken` apparaît). **Ne jamais les mettre dans un fichier du repo.**
2. Variables :

```powershell
$env:AWS_REGION="ca-central-1"            # region indiquee par les organisateurs
$env:BEDROCK_MODEL_ID="<id copie depuis la console Bedrock>"
$env:ALPHAFORGE_BUCKET="<nom du compartiment S3>"     # facultatif : traces dans S3
$env:ALPHAFORGE_LAMBDA="alphaforge-machine"           # facultatif : calculs dans Lambda
streamlit run app.py
```

3. Déploiement Lambda : voir `scripts/deploiement_aws.md`.

## Données

Jeu de départ AlphaForge fourni par les organisateurs (`data/`, voir `data/README_donnees.md`) : prix Yahoo Finance (`adj_close`), USD/CAD Banque du Canada, 12 nov. 2021 → 12 nov. 2026.

Choix de méthode : rendements sur `adj_close` ; conversion en CAD avec le taux de la Banque du Canada (dernier taux connu reporté les jours sans publication) ; volatilité annualisée sur 252 jours (365 pour la crypto) ; fenêtres glissantes plafonnées à 3 ans faute d'historique.

## Limites connues

Une seule période historique (le passé ne prédit pas l'avenir) ; biais du survivant (actifs choisis en 2026) ; aucune donnée ESG fournie (le système signale l'information manquante au lieu d'inventer) ; seuils des contrats = hypothèses de l'équipe ; portefeuilles achetés et conservés, sans rééquilibrage ni frais.

## Transparence

Des assistants d'IA ont été utilisés pour accélérer l'écriture du code et de la documentation ; l'équipe a relu, testé et validé les résultats.
