# Alliance Transit

Gestion du transit, du transport et de la douane (Guinée). Interface web (`public/`) et API FastAPI (`app/`, servie sous `/api`).

## Déployer sur Vercel
1. Poussez ce dossier sur GitHub, GitLab ou Bitbucket.
2. Sur vercel.com : **Add New > Project**, importez le dépôt. Aucun réglage de build n'est nécessaire.
3. Créez une base PostgreSQL : onglet **Storage** du projet, puis Neon (Marketplace). Copiez l'URL de connexion (de préférence l'URL « pooled ») dans la variable `DATABASE_URL`.
4. Ajoutez les variables d'environnement (voir `.env.example`) : `DATABASE_URL`, `SECRET_KEY` (`openssl rand -hex 32`), `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
5. Déployez. Au premier appel, les tables et le compte administrateur sont créés automatiquement.
6. Vérifiez : `https://<votre-projet>.vercel.app/api/health` puis `/api/docs`.

En ligne de commande : `npm i -g vercel && vercel --prod`.

L'API refuse de démarrer sur Vercel si `SECRET_KEY` ou `ADMIN_PASSWORD` manque.

## Limites de l'hébergement Vercel à connaître
- Les fonctions n'ont pas de disque persistant : les documents sont stockés dans PostgreSQL. Taille limitée à 4 Mo par fichier (plafond de Vercel : 4,5 Mo par requête). Pour des scans plus lourds, passer à un stockage objet (Vercel Blob, S3).
- Démarrage à froid : le premier appel après une période d'inactivité est plus lent.
- Durée maximale d'un appel : 30 s (réglable dans `vercel.json` selon le plan).
- Données de santé de l'application, sauvegardes et conservation de 10 ans : à assurer côté fournisseur PostgreSQL (sauvegardes automatiques, exports réguliers).
- Souveraineté des données : choisissez la région de la base selon vos exigences (point 17 du cahier des charges).

## Interface
`public/index.html` est le prototype : il fonctionne en mode démonstration, avec ses données dans le navigateur. Le brancher sur l'API (connexion, dossiers, douane, facturation) est l'étape suivante.

## Développement local
    python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
    uvicorn app.main:app --reload     # SQLite par défaut, documentation sur /docs
    pytest

Avec Docker : `DB_PASSWORD=... SECRET_KEY=... ADMIN_PASSWORD=... docker compose up -d --build`

## État par rapport au cahier des charges
Fait : clients et utilisateurs (8 rôles), dossiers, documents, transit, douane (liquidation, contrôles, messages), facturation multi-devises, tableau de bord, audit, paramétrage des taxes.
À faire : liaison réelle avec SYDONIA World (`app/gateway.py`, simulée), interface branchée sur l'API et portail client, application mobile chauffeur, GPS et SMS/WhatsApp, migrations Alembic.

Taux de change, redevance statistique et prélèvement CEDEAO sont des valeurs d'exemple (`app/customs.py`, modifiables par `PUT /api/params`) : à caler sur une quittance SYDONIA réelle.
