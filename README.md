# AlphaForge AI — Vivez votre placement avant de le faire

**Datathon PolyFinances 2026 · Banque Nationale × AWS**
Simulation uniquement : personas fictifs, aucune transaction, aucun conseil financier personnalisé.

- **Application en ligne :** http://98.80.14.243:8501
- **Dépôt GitHub :** https://github.com/Celestine23/alphaforge-ai-equipe25
- **Installer et lancer en local :** voir la section [Installation](#installation) ci-dessous.

L'assistant fait **vivre** à l'investisseur ce que son placement lui aurait fait traverser (relecture des données 2021-2026, en CAD), **conteste** quand le placement ne respecte pas son contrat d'investisseur, et **prouve** chaque chiffre avec un reçu numéroté (#R-001…) contrôlé par un Vérificateur.

## Ce que voit l'utilisateur

1. **Il choisit un profil** dans la barre latérale : Robert, Mateo ou Amira (les personas du défi), ou **« ➕ Mon profil »** pour décrire un profil fictif en quelques questions simples (horizon, perte acceptée, épargne, préférences ESG et crypto). L'application en déduit un profil prudent, équilibré ou audacieux.
2. **Il dit ce qu'il veut faire**, de deux façons au choix :
   - **« 🔎 Choisir un placement »** : une liste des 31 placements des données (le symbole, puis une description simple : « ESGV : Un fonds américain qui exclut les entreprises controversées »), plus le montant et l'horizon, puis « Voir le résultat » ; aucune phrase à écrire ;
   - **la conversation**, en langage courant, par exemple : *« Je veux mettre 60 000 $ dans Tesla, j'en aurai besoin dans 4 ans. »* S'il manque une information (l'horizon, par exemple), l'Intervieweur pose la question ; si le placement n'est pas dans les données, il le dit et renvoie vers la liste.

   **Il ne sait pas quoi choisir ?** Avec l'option « Je ne sais pas » de la liste, ou en écrivant *« je ne sais pas »*, l'application rejoue 8 placements courants (fonds larges, obligations, or) sur son profil et affiche ceux qui lui conviennent. Ce sont des exemples en simulation, pas une recommandation d'achat.

   Si l'horizon donné dans la demande diffère de celui du profil (Mateo : environ 10 ans, mais « 15 ans » pour ce placement), le calcul utilise ce que la personne a dit, et l'application le signale clairement.
3. **Il lit le résultat dans trois onglets :**

| Onglet | Pour qui | Contenu |
| --- | --- | --- |
| 💬 **Pour vous** | L'investisseur, même sans connaissances financières | Le verdict en mots simples ; ce qu'il aurait vécu, en dollars et en mois (pire moment, perte sur le papier, temps pour revenir à sa mise) ; pourquoi c'est important pour lui ; un graphique « votre choix / option plus adaptée » ; deux options conformes à son profil |
| 🔁 **Et si…** | L'investisseur curieux | Changer l'horizon ou le montant : la Machine recalcule et les règles rendent un nouveau verdict |
| 🧾 **Les preuves** | Le jury, un conseiller, un auditeur | Le contrat (hypothèses), les règles vérifiées, les reçus cliquables (calcul, source, période, devise), la carte de vérité de l'Explicateur, le score de fidélité, la trace d'exécution |

Toutes les phrases de l'onglet « Pour vous » sont construites par le code à partir des reçus : aucun chiffre n'y est inventé.

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

## Installation

Prérequis : Python 3.12 ou plus récent, Git.

```bash
git clone https://github.com/Celestine23/alphaforge-ai-equipe25.git
cd alphaforge-ai-equipe25
python3 -m venv .venv
# Mac / Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Dépendances (`requirements.txt`) : pandas, numpy, streamlit (1.50 ou plus récent), altair, boto3, strands-agents.

## Démarrage rapide (sans AWS, pour tester)

Le mode hors ligne remplace les agents IA par des textes gabarits ; les calculs, le verdict et les reçus sont identiques.

```bash
# Mac / Linux
ALPHAFORGE_HORS_LIGNE=1 python scripts/test_rapide.py
ALPHAFORGE_HORS_LIGNE=1 streamlit run app.py
# Windows PowerShell
$env:ALPHAFORGE_HORS_LIGNE="1"; python scripts/test_rapide.py
$env:ALPHAFORGE_HORS_LIGNE="1"; streamlit run app.py
```

L'application s'ouvre sur `http://localhost:8501`. Pour l'arrêter : **Ctrl + C** dans le terminal.

## Avec AWS (Bedrock, Lambda, S3)

1. Identifiants du compte d'équipe : page Workshop Studio → **Get AWS CLI credentials** → copier les variables dans le terminal (elles expirent : les recopier si une erreur `ExpiredToken` apparaît). **Ne jamais les mettre dans un fichier du repo.**
2. Variables, puis lancement :

```bash
# Mac / Linux
export AWS_REGION="us-east-1"                       # région du compte d'équipe
export BEDROCK_MODEL_ID="us.amazon.nova-pro-v1:0"
export ALPHAFORGE_BUCKET="alphaforge-equipe25-2026"   # traces dans S3
export ALPHAFORGE_LAMBDA="alphaforge-machine"        # facultatif : calculs dans Lambda
streamlit run app.py
```

```powershell
# Windows PowerShell
$env:AWS_REGION="us-east-1"
$env:BEDROCK_MODEL_ID="us.amazon.nova-pro-v1:0"
$env:ALPHAFORGE_BUCKET="alphaforge-equipe25-2026"
$env:ALPHAFORGE_LAMBDA="alphaforge-machine"
streamlit run app.py
```

3. Déploiement Lambda : voir `scripts/deploiement_aws.md`.

Note : la Lambda déployée connaît les trois personas du défi. Un profil créé avec « ➕ Mon profil » est calculé localement, avec le même code ; l'onglet « Les preuves » l'indique.

## Scénarios de validation

`docs/scenarios.md` liste les demandes de démonstration et le verdict attendu pour chacune (tests d'acceptation). Résumé :

| Profil | Demande | Verdict attendu |
| --- | --- | --- |
| Robert | 60 000 $ dans Tesla, besoin dans 4 ans | Incohérent (« Ce placement ne vous convient pas ») |
| Robert | même demande, « Et si… » horizon 12 ans | À surveiller |
| Robert | 60 000 $ dans ZST, besoin dans 4 ans | Cohérent |
| Amira | 60 000 $ dans Tesla, besoin dans 15 ans | À surveiller (concentration) |
| Amira | 15 000 $ en Bitcoin, besoin dans 15 ans | Incohérent (plafond crypto) |
| Amira | 10 000 $ en Bitcoin, besoin dans 15 ans | À surveiller |
| Mateo | 30 000 $ dans Exxon, besoin dans 10 ans | À surveiller (information ESG manquante) |

## Données

Jeu de départ AlphaForge fourni par les organisateurs (`data/`, voir `data/README_donnees.md`) : prix Yahoo Finance (`adj_close`), USD/CAD Banque du Canada, 12 nov. 2021 → 12 nov. 2026.

Choix de méthode : rendements sur `adj_close` ; conversion en CAD avec le taux de la Banque du Canada (dernier taux connu reporté les jours sans publication) ; volatilité annualisée sur 252 jours (365 pour la crypto) ; fenêtres glissantes plafonnées à 3 ans faute d'historique.

## Limites connues

Une seule période historique (le passé ne prédit pas l'avenir) ; biais du survivant (actifs choisis en 2026) ; aucune donnée ESG fournie (le système signale l'information manquante au lieu d'inventer) ; seuils des contrats = hypothèses de l'équipe, y compris ceux déduits pour « Mon profil » ; portefeuilles achetés et conservés, sans rééquilibrage ni frais ; un placement isolé est évalué, sans tenir compte du reste du portefeuille de la personne.

## Transparence

Des assistants d'IA ont été utilisés pour accélérer l'écriture du code et de la documentation ; l'équipe a relu, testé et validé les résultats.
