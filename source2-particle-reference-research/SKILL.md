---
name: source2-particle-reference-research
description: "Research native particle, material and texture examples in local CS2 or Deadlock VPKs using bounded extraction, provenance and offline observations."
---

# Rechercher des références Source 2

Transformer des ressources locales en faits vérifiables utiles à l’écriture de nouvelles particules. Une ressource observée dans Deadlock est une piste pour CS2 ; sa présence ne prouve ni l’existence de la classe, ni les mêmes propriétés ou valeurs par défaut dans CS2.

## Consulter les observations déjà livrées

Lire [la couverture et les limites des observations CS2/Deadlock](references/native-vpk-observations.md), puis interroger uniquement la classe utile avec le helper portable. Il ne nécessite ni jeu installé, ni Node, ni connexion réseau :

```text
python scripts/query_observations.py --game cs2 --search Render --limit 20
python scripts/query_observations.py --game cs2 --class C_OP_RenderSprites --stage m_Renderers
python scripts/query_observations.py --game cs2 --class C_OP_RenderSprites --field "m_vecTexturesInput[].m_hTexture"
python scripts/query_observations.py --game deadlock --class C_OP_RenderLightBeam --stage m_Renderers
```

`--search` porte sur les noms de classe/étape de l’index, sans lire toutes les fiches ni rechercher leurs champs. `--class` renvoie par défaut un résumé et au plus `--limit` noms de champs, pas leurs milliers de valeurs. `--field` sélectionne un chemin exact, avec `[]` pour les tableaux, et donne son témoin avec hash du payload. Chaque fiche lue est vérifiée contre sa taille et son SHA-256 déclarés dans l’index. Un snapshot local peut être sélectionné explicitement par `--references`. Lectures bornées à 4 MiB par fichier et sortie JSON à 128 KiB ; si la sortie est trop grande, demander un champ précis ou réduire `--limit`.

Les fiches intégrées contiennent des observations, pas toutes les propriétés déclarées par le moteur. Utiliser la recherche locale dans les VPK ci-dessous pour compléter un cas absent, puis croiser le résultat avec le schéma du jeu cible.

## Trouver et sélectionner

Partir du jeu cible, de son build et du chemin du VPK fournis ou découverts dans une installation locale. Lire les archives en place ; écrire les extractions dans un nouveau dossier de travail explicite. Ne pas supposer qu’un corpus déjà décompilé est à jour.

Le helper inclus exige Python 3.10+ sans dépendance. Depuis ce dossier de skill :

```text
python scripts/vpk_reference.py inventory --vpk "CHEMIN/pak01_dir.vpk" --extension vpcf_c --limit 20
python scripts/vpk_reference.py inventory --vpk "CHEMIN/pak01_dir.vpk" --extension vpcf_c --prefix particles/ --limit 100
python scripts/vpk_reference.py inventory --vpk "CHEMIN/pak01_dir.vpk" --extension vpcf_c --contains smoke --limit 20
python scripts/vpk_reference.py inventory --vpk "CHEMIN/pak01_dir.vpk" --extension vmat_c --extension vtex_c --prefix materials/particle/ --limit 20
```

L’inventaire compte toutes les extensions du VPK, puis applique les filtres à la liste. `--contains` recherche un fragment littéral de chemin sans regex. `--limit 0` produit seulement les comptes et la provenance. À ce stade, les CRC32 sont déclarés par l’index, sans vérification des payloads ; un nom de fichier donne un candidat, pas son apparence réelle. Ne pas limiter systématiquement les particules au dossier `particles/` : les deux jeux étudiés ont aussi des `.vpcf_c` ailleurs.

Choisir quelques effets correspondant au besoin visuel, puis suivre leurs enfants, textures, matériaux, modèles et autres ressources référencées. Pour une recherche exhaustive, conserver les agrégats et les erreurs par fichier plutôt que charger toutes les ressources dans le contexte.

## Extraire et inspecter

```text
python scripts/vpk_reference.py extract --vpk "CHEMIN/pak01_dir.vpk" --entry particles/exemple.vpcf_c --output "TRAVAIL/nouvelle-extraction"
```

Répéter `--entry` pour sélectionner plusieurs chemins exacts issus de l’inventaire. Le dossier parent doit exister ; le dossier de sortie doit être nouveau. L’extraction associe preload et données, vérifie le CRC32 et produit `vpk-reference-manifest.json` avec SHA-256 par ressource. Bornes : index 64 MiB, un million d’entrées, chaîne 4096 octets ; extraction 64 fichiers, 64 MiB par fichier, 256 MiB au total. Aucun contenu de VPK n’est exécuté, téléchargé ou décompilé par ce script. Il ne vérifie pas les signatures ou sections MD5 du VPK.

Les fichiers `*_c` sont compilés. Utiliser un **Source2Viewer-CLI/ValveResourceFormat déjà installé**, compatible avec leur version. Vérifier d’abord son aide et sa version ; les interfaces changent :

```text
Source2Viewer-CLI --help
Source2Viewer-CLI --version
Source2Viewer-CLI --input "TRAVAIL/nouvelle-extraction/particles/exemple.vpcf_c" --block DATA
```

La dernière commande a été vérifiée avec VRF 19.2.0. Son résultat contient aussi le résumé et les références externes : ne pas traiter toute sa sortie comme du KV3 brut. Pour produire un fichier source ou résoudre des dépendances, suivre l’aide de **la version installée** et garder toutes les sorties dans le dossier de travail. Une copie extraite hors du jeu peut perdre la résolution des dépendances ; ne pas interpréter cela comme une absence dans le VPK. Voir le [guide officiel VRF](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/command-line.md).

Pour une recherche reproductible, le helper autonome `scripts/inspect_vpk_with_vrf.py` effectue ces contrôles, lit les payloads avec CRC32 et produit un snapshot local de transcriptions DATA, hashes, formats et couverture. Il nécessite seulement les scripts de ce skill, Python standard library et VRF déjà installé :

```text
python scripts/inspect_vpk_with_vrf.py --vpk "CHEMIN/pak01_dir.vpk" --vrf "OUTILS/Source2Viewer-CLI.exe" --game cs2 --entry particles/exemple.vpcf_c --output "TRAVAIL/inspection-neuve"
```

Pour sélectionner toutes les particules d’un index, utiliser `--all-particles --max-files 20000` à la place de `--entry`. Les limites cumulatives et erreurs restent explicites ; seul `coverage.complete = true` confirme que toute la sélection demandée a été inspectée. Le code de sortie 2 signale une couverture incomplète. Lire [la procédure autonome et ses limites](references/native-vpk-observations.md#independent-reproduction-with-the-bundled-tools) avant un scan complet. Cette méthode VRF indépendante fournit de nouvelles preuves textuelles ; elle ne recrée pas à l’identique les agrégats historiques issus du décodage binaire.

## Convertir l’observation en connaissance

Pour un candidat trouvé seulement dans l’index, conserver jeu/build, chemin, hash de l’index et CRC déclaré non vérifié. Pour une ressource réellement lue, ajouter SHA-256 du payload et contrôle CRC ; pour une propriété inspectée, noter aussi décodeur/version, classe et étape, chemin exact de propriété, type observé, contexte et limites. Distinguer :

- **observé dans une ressource** : nom, type et valeur présents dans ce fichier ;
- **déclaré par le schéma** : type, enum et défaut du schéma de cette version ;
- **accepté par le compilateur cible** : sortie fraîche relue ;
- **vérifié visuellement dans le moteur cible** : protocole, capture et résultat.

Une propriété absente peut être supprimée par le compilateur. Une valeur observée ne devient pas un défaut global. Un exit code 0 peut accompagner une propriété inconnue supprimée silencieusement. Un nom commun à deux jeux ne prouve pas la même sémantique. Conserver les faits inconnus comme inconnus.

Pour reproduire le principe d’un effet, décrire ses couches, chronologie, CP, providers, rendus et dépendances ; écrire ensuite ses propres sources et assets. Garder les ressources originales localement. Le dépôt de skills contient la méthode, des métadonnées et des exemples originaux, sans recopier les assets du jeu.

Lire [les observations d’ingestion vérifiées](references/vpk-ingestion-2026-10-15.md) pour les builds et preuves utilisés pendant la création de ce skill. Ces observations ne constituent pas un catalogue exhaustif des propriétés.

## Vérifier le helper

```text
python -m unittest discover -s scripts -p "test_*.py" -v
```
