# Ingestion locale vérifiée le 15 octobre 2026

Les comptes proviennent des index réellement installés, pas d’un dépôt décompilé ancien. Le JSON associé contient les identifiants d’index et les hashes des deux extractions de contrôle : [vpk-ingestion-2026-10-15.json](vpk-ingestion-2026-10-15.json).

| Jeu | Build Steam installé observé | Entrées totales dans `pak01_dir.vpk` | `.vpcf_c` | `.vmat_c` | `.vtex_c` |
| --- | ---: | ---: | ---: | ---: | ---: |
| Counter-Strike 2 | 25640462 | 137440 | 2622 | 22008 | 71714 |
| Deadlock | 25660886 | 137966 | 16310 | 4412 | 14191 |

Un inventaire du VPK ne couvre pas automatiquement les autres archives, addons, ressources séparées ou fonctionnalités possibles du moteur. Les builds ont été lus dans `appmanifest_730.acf` et `appmanifest_1422450.acf` de l’installation locale ; l’identité reproductible de l’index est son SHA-256, dont le périmètre est explicitement limité à l’en-tête et l’arbre.

## Contrôles réalisés

Le helper standard library a lu les deux index v2 et extrait exactement une particule dans chacun, dans des dossiers de travail nouveaux, avec CRC32 correct. Les originaux extraits restent dans des dossiers locaux de recherche ; ils ne font pas partie du skill.

VRF installé : `19.2.0+f86ea981fc37b9f8f23c4eb84e058de2083b6761`. Les flags `--input`, `--block`, `--help` et `--version` ont été confirmés par l’aide de cet exécutable, puis `--block DATA` exécuté sur les deux extractions.

| Contrôle | CS2 | Deadlock |
| --- | --- | --- |
| Chemin exact | `particles/ambient/ambient_water_stream.vpcf_c` | `materials/dev/steam_test.vpcf_c` |
| Octets du payload | 4016 | 3207 |
| Resource Type / Header | Particle v1 / header 12 | Particle v1 / header 12 |
| Format DATA affiché par VRF | `vpcf54` | `vpcf61` |
| Classes de rendu présentes | `C_OP_RenderTrails` | `C_OP_RenderSprites` |
| Références externes affichées | Une texture et cinq enfants particules | Une texture |

Deux enseignements utiles à la recherche :

- Les particules ne sont pas toutes rangées sous `particles/` : le contrôle Deadlock est sous `materials/dev/` et l’inventaire CS2 contient notamment une particule sous `models/gameplay/`.
- Ces deux exemples utilisent des formats VPCF distincts malgré un même header de ressource. Cela suffit pour exiger une vérification du décodage et du jeu cible ; cela ne prouve pas l’incompatibilité de toutes les propriétés entre les jeux.

Ces observations démontrent l’accès reproductible aux références et l’inspection de leur structure. Elles ne prouvent ni la sémantique exacte des propriétés, ni une équivalence visuelle, ni la disponibilité d’une fonctionnalité Deadlock dans CS2.

## Reproduire

Depuis le dossier du skill, remplacer les chemins d’installation et de travail :

```text
python scripts/vpk_reference.py inventory --vpk "CS2/game/csgo/pak01_dir.vpk" --extension vpcf_c --limit 0
python scripts/vpk_reference.py inventory --vpk "Deadlock/game/citadel/pak01_dir.vpk" --extension vpcf_c --limit 0
python scripts/vpk_reference.py extract --vpk "CS2/game/csgo/pak01_dir.vpk" --entry particles/ambient/ambient_water_stream.vpcf_c --output "TRAVAIL/cs2-sample-neuf"
python scripts/vpk_reference.py extract --vpk "Deadlock/game/citadel/pak01_dir.vpk" --entry materials/dev/steam_test.vpcf_c --output "TRAVAIL/deadlock-sample-neuf"
Source2Viewer-CLI --help
Source2Viewer-CLI --version
Source2Viewer-CLI --input "TRAVAIL/cs2-sample-neuf/particles/ambient/ambient_water_stream.vpcf_c" --block DATA
Source2Viewer-CLI --input "TRAVAIL/deadlock-sample-neuf/materials/dev/steam_test.vpcf_c" --block DATA
```

Références d’outillage : [ValvePak](https://github.com/ValveResourceFormat/ValvePak), [VRF CLI](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/command-line.md). Le helper ne dépend pas de ces projets ; VRF est utilisé ici séparément pour inspecter DATA.
