# Déploiement AWS — pas à pas (Responsable Cloud)

Tout se fait dans **une seule région** : **`us-east-1`** (région du compte d'équipe fourni par les organisateurs).

## 0. Accès au compte d'équipe (5 min)
1. https://catalog.workshops.aws/join → code d'accès reçu par courriel → se connecter.
2. Menu de gauche : **Open AWS console**. Vérifier la région en haut à droite.
3. Pour travailler depuis un portable : **Get AWS CLI credentials** → copier les variables d'environnement.

## 1. Bedrock (15 min) — à faire EN PREMIER
1. Console → **Amazon Bedrock** → *Model catalog*. Choisir un modèle disponible dans la région
   (si un modèle demande un formulaire d'accès, commencer avec un modèle **Amazon Nova**).
2. Copier son **Model ID** (ou l'ID du *inference profile* si la console l'indique).
3. Test depuis le portable :
```powershell
pip install strands-agents boto3
$env:AWS_REGION="us-east-1"; $env:BEDROCK_MODEL_ID="us.amazon.nova-pro-v1:0"
python -c "from strands import Agent; from strands.models import BedrockModel; import os; print(Agent(model=BedrockModel(model_id=os.environ['BEDROCK_MODEL_ID'], region_name=os.environ['AWS_REGION']), callback_handler=None)('Dis bonjour en une phrase.'))"
```
Résultat attendu : une phrase de bonjour. Sinon : vérifier l'ID, la région, les identifiants (expirés ?).

## 2. S3 (10 min)
```powershell
aws s3 mb s3://alphaforge-equipe25-2026 --region us-east-1
aws s3 cp data/ s3://alphaforge-equipe25-2026/data/ --recursive
```
(Sans AWS CLI : console S3 → *Create bucket* → *Upload* du dossier `data`.)

## 3. Lambda (30 min)
1. Créer le paquet (depuis la racine du repo) :
```powershell
Compress-Archive -Path lambda_function.py, alphaforge -DestinationPath lambda.zip -Force   # Windows
# zip -r lambda.zip lambda_function.py alphaforge                                         # Mac/Linux
```
2. Console → **Lambda** → *Create function* → nom `alphaforge-machine`, runtime **Python 3.12**.
3. *Upload from* → `.zip` → `lambda.zip`. Handler : `lambda_function.lambda_handler`.
4. *Layers* → *Add a layer* → *AWS layers* → **AWSSDKPandas-Python312** (fournit pandas et numpy).
5. *Configuration* → *General* : mémoire **1024 Mo**, délai **60 s**.
   *Environment variables* : `ALPHAFORGE_BUCKET = alphaforge-equipe25-2026`.
6. *Permissions* → rôle d'exécution → ajouter une politique **en lecture seule** sur `arn:aws:s3:::alphaforge-equipe25-2026/data/*` (moindre privilège).
7. *Test* avec l'événement : `{"persona": "Robert", "ticker": "TSLA", "montant": 60000, "besoin": 4}`
   Résultat attendu : un JSON avec `"verdict": "Incoherent"`. Les journaux apparaissent dans **CloudWatch** (onglet *Monitor*).
8. Côté application : `$env:ALPHAFORGE_LAMBDA="alphaforge-machine"`.

## 4. Traces dans S3
`$env:ALPHAFORGE_BUCKET="alphaforge-equipe25-2026"` → chaque analyse écrit `traces/<date>-<persona>.json` dans S3.

## 5. (Facultatif, dimanche matin) Héberger l'app sur EC2
1. EC2 → *Launch instance* → Amazon Linux 2023, **t3.small**, rôle IAM avec `bedrock:InvokeModel`, `lambda:InvokeFunction`, `s3:PutObject` sur le compartiment.
2. Groupe de sécurité : ouvrir le port **8501**.
3. *Connect* → EC2 Instance Connect, puis :
```bash
sudo dnf install -y git python3-pip
git clone https://github.com/Celestine23/alphaforge-ai-equipe25.git && cd alphaforge-ai-equipe25
pip3 install -r requirements.txt
export AWS_REGION=us-east-1 BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0 ALPHAFORGE_BUCKET=alphaforge-equipe25-2026 ALPHAFORGE_LAMBDA=alphaforge-machine
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &
```
4. Ouvrir `http://<IP publique>:8501`.

## 6. Dimanche soir : export AVANT la suppression du compte
```powershell
aws s3 sync s3://alphaforge-equipe25-2026 ./export_aws
```
+ captures d'écran : console Lambda (test réussi), CloudWatch (journaux), S3 (traces), Bedrock.
Le compte est supprimé lundi à 13h59 : rien ne pourra être récupéré après.
