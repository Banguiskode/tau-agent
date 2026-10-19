# Tau Agent

Harness indépendant pour agents LLM — Hermès, Claude Code et runtimes
compatibles — avec replay déterministe, mutations négatives et portes Tau.

## Agent Tau

La partie principale n'est pas ce harness Python. C'est l'agent, écrit en Tau,
à la façon d'Hermès ou de Jido, mais la politique est une spec.

- Un signal est un flux d'entrée. Ici, un résultat d'outil.
- Une directive est un flux de sortie. Ici, l'arrêt.
- L'hôte substitue les chemins, lance `r`, lit le fichier. Il ne choisit pas.
- Un bit que la loi n'a pas forcé n'est pas une directive.

La première loi est déjà mesurée. Le signal `0 0 1 0` imprime l'arrêt
`0 0 0 1`. Un appel au pas d'après est `unsat`.

Le pas de l'agent est une autre spec. Une demande sans résultat imprime
un appel et un seul outil. Un résultat imprime l'arrêt, et éteint l'appel.
L'hôte n'exécute que l'outil imprimé, puis renvoie le résultat comme signal.
La ligne d'après dans le fichier n'est pas une directive. L'autre outil,
ou un appel malgré le résultat, est `unsat`.

Le même pas tient dans un seul `r`. Tau imprime l'appel, puis attend.
L'hôte lance le script de l'outil imprimé, pas l'autre, et envoie sa sortie.
Un 1 imprime l'arrêt. Un 0 ne l'imprime pas, et ne relance pas l'appel.
L'indice 2 du fichier n'est pas une directive. L'outil travaille : il dit
si un fichier est non vide, ou si un chemin est un dossier. L'hôte envoie
la sortie du script, pas le texte du fichier. Une sortie qui n'est pas un
bit n'est pas convertie.

## Objectif

Vérifier la trajectoire complète d'un agent, pas seulement son texte final :

```text
LLM → appel d'outil → résultat → décision → état terminal
```

## Démarrage rapide

```bash
python3 -m unittest discover -s scripts -p 'test_llm_*.py' -v
python3 scripts/llm_harness.py docs/llm_harness_example.jsonl \
  --allow-tool tau_real_portfolio_gate
```

## Adapter et rejouer une trace Hermès

```bash
python3 scripts/llm_adapters.py hermes \
  docs/hermes_trace_example.jsonl /tmp/hermes_normalized.jsonl
python3 scripts/llm_replay.py /tmp/hermes_normalized.jsonl \
  docs/hermes_replay_fixtures.json
```

## Tester les comportements interdits

```bash
python3 scripts/llm_mutations.py /tmp/hermes_normalized.jsonl \
  disallowed_tool /tmp/mutated.jsonl
python3 scripts/llm_harness.py /tmp/mutated.jsonl \
  --allow-tool tau_real_portfolio_gate
```

Le dernier contrôle doit échouer : un échec sur une trace mutée est une preuve
que la porte rejette le comportement interdit.

## Matrice de mutations

`mutation_matrix.py` vérifie un cas nominal et quatre trajectoires fautives.
La matrice ne passe que si le nominal est accepté et si toutes les mutations
sont rejetées.

```bash
python3 scripts/mutation_matrix.py docs/hermes_trace_canonical.jsonl \
  docs/hermes_replay_fixtures.json \
  --allow-tool tau_real_portfolio_gate
```

## Comparaison d'agents

`compare_agents.py` applique le même replay et la même porte Tau à plusieurs
traces. Le manifest distingue les agents et leurs fixtures, afin de comparer
leurs trajectoires sans confondre une différence d'adaptateur avec une
différence de comportement.

```bash
python3 scripts/compare_agents.py docs/agent_comparison.json
```

## Porte de mission complète

La commande `scripts/mission_gate.py` enchaîne les trois niveaux : validation de
trace, replay déterministe, puis porte Tau. Elle ne lance Tau que si les deux
premières portes sont vertes.

```bash
python3 scripts/mission_gate.py docs/hermes_trace_canonical.jsonl \
  docs/hermes_replay_fixtures.json \
  --allow-tool tau_real_portfolio_gate
```

Le verdict est écrit dans `mission_verdict.json`. Un seul échec bloque la
mission et indique la couche fautive.

## Porte Tau émise depuis la trace

La mission ne rejoue pas un noyau figé. `scripts/emit_tau_trace.py` construit la
spec depuis la trace canonique : un fait ponctuel par pas, un lien indexé vers
l'appel du même `call_id`, et une mutation qui ajoute une négation au noyau
intact. Un appel sans décision antérieure vise l'indice 0, déjà épinglé à 0 :
le noyau est alors `UNSAT`.

```bash
python3 scripts/run_tau_gate.py --trace docs/hermes_trace_canonical.jsonl
```

`scripts/mission_gate.py` et `scripts/compare_agents.py` passent chacun par ce
chemin. Deux agents ne partagent plus le même verdict Tau.

## Synthèse au cœur

Le trajet entier tient dans un seul `solve`, pas dans une boucle Python.
`scripts/synthesize_step.py --window` donne la politique sur quatre pas.
Tau choisit les bits. Le harness lit le témoin. Un appel au pas 0 rend
`no solution` : ce pas n'est pas inventé.

L'interpréteur `r` avec un regard en arrière n'est pas ce refus. Mesuré :
un appel épinglé au pas 0 a quand même été exécuté. La fenêtre `solve`
est le produit. La porte `r` reste la vérification après coup.

```bash
python3 scripts/synthesize_step.py --window
```

Témoin mesuré : décision, appel, résultat, fin. Une mission, un appel.
Les positions ne sont pas écrites par Python.

## Révision par point

La spec qui tourne accepte un changement sans être réécrite en Python.
`scripts/revise_point.py` envoie les propositions au flux `u`. Tau fusionne
une proposition satisfiable et refuse une proposition contradictoire
(`u := F`, la règle n'est pas appliquée). Le pas de la mise à jour peut
encore montrer l'ancienne loi. Le pas d'après obéit à la loi nouvelle.
L'exclusion complète reste dans la spec fusionnée.

```bash
python3 scripts/revise_point.py
```

Mesuré : la contradiction `c[t] = 0 && c[t] = 1` est refusée, le pas reste
un seul événement. `a[t] = 1` est fusionné. Les deux pas suivants sont la
décision seule, les trois autres bits à 0.

Une proposition satisfiable qui contredit la spec en cours gagne.
`a[t] = 0` après `a[t] = 1` est accepté. L'ancienne loi tombe. L'exclusion
tombe avec elle : le pas d'après ne porte plus que `a = 0`. Le rapport
écrit `exclusion_kept: false`. Ne pas dire que le reste a tenu.

Pour garder l'exclusion, la répéter dans la même proposition.
`a[t] = 0 &&` l'exclusion complète est accepté, l'ancienne loi tombe, et
le pas d'après reste un seul événement avec `a = 0`. Le rapport écrit
`exclusion_kept: true`. Sans cette répétition, elle ne tient pas.

## Révision d'une session réelle

`u` n'a pas gardé l'appel observé : le pin `c[1]` a été réécrit. Le chemin
qui tient est un `solve`. Le préfixe de `docs/trajectories/local_session.jsonl`
est épinglé, sans le texte. La loi nouvelle est `d3' & s2 = 0`, pas `d3 = 1`.
Tau remplit la fin. La session enregistrée continuait par une décision.
Le témoin, lui, s'arrête. Nier l'appel observé rend `no solution`.

Deux points d'affilée, sur une session réelle à deux appels
(`20260709_173642_12633c`, sans texte). Après le premier résultat, Tau
remplit une décision, puis la fin. Le second appel enregistré n'est pas
rejoué. Casser la chaîne (`a3 = 0`) rend `no solution`. 0,2 s.

```bash
python3 scripts/revise_session.py --chain
```

Tau choisit le point. Python n'écrit pas `p4 = 1`. Sur la session à deux
appels, le point choisi est le second appel. Le début est gardé. Ce pas
n'est plus un appel. Sur la session à un seul appel, il n'y a pas de point :
`no solution`, rien n'est inventé.

```bash
python3 scripts/revise_session.py --choose
```

Tau choisit aussi la règle. Deux règles sont proposées, aucune n'est
épinglée : second appel, ou seconde décision. Sur la session à deux appels,
les deux sont légales ; ce passage a choisi la seconde décision, au pas 3.
Sur la session réelle à un appel puis une seconde décision, seule cette
règle tient, au pas 3. Sur un trajet sans seconde décision ni second appel,
`no solution`.

```bash
python3 scripts/revise_session.py --rule
```

Tau écrit une règle qui n'est pas dans la source. Le fait observé, une
seconde décision, est `o2[t] = 1`. Le flux Tau n'accepte ici que des noms
`i`, `o`, `this` ou `u`. Tau rend le dual : `sometimes o2[t]' != 0`.
La source ne contient pas `sometimes`. Un nom illégal n'écrit rien.

```bash
python3 scripts/write_rule.py
```

Le dual est réinstallé sur le bit de la session. L'étiquette `:tau` est
retirée, la clause non. Tau la fusionne en `sometimes o2[t]:sbf' != 0`.
Au pas 3, celui de la seconde décision, le bit vaut 0. Sans règle, rien
n'est réinstallé.

Tau choisit alors l'événement. L'équation interdit la décision, pas le
remplaçant. Ce passage remplit un résultat. Sans l'interdiction, la
décision enregistrée reste possible. Un trajet sans seconde décision
n'a pas de remplaçant.

Les trois autres événements sont légaux : appel, résultat, fin. La
décision ne l'est pas. Un seul témoin n'est pas l'ensemble.

Une mission choisit parmi les trois. Elle interdit, elle n'épingle pas.
« Pas d'appel et pas de résultat » laisse la fin. « Pas de résultat et
pas de fin » laisse l'appel. « Pas d'appel et pas de fin » laisse le
résultat. Interdire les trois rend `no solution`.

Tau tire la mission du trajet. Le pas enregistré juste après est le fait.
Les interdits ne sont pas épinglés. La session qui finit interdit l'appel
et le résultat, et garde la fin. La session qui rappelle interdit le
résultat et la fin, et garde l'appel.

Tau décide s'il garde le pas enregistré. `m` n'est pas épinglé. Les deux
choix sont possibles. Ce passage écarte le pas, et met un résultat. Garder
la décision interdite est impossible.

La raison est la loi déjà écrite : après un résultat, on s'arrête.
`d3' & s2 = 0` n'épingle ni `m` ni la fin. La session qui finissait
garde ce pas. La session qui rappelait l'écarte, et Tau met une fin.

Tau choisit la loi. `n0 = 1` et `n1 = 1` ne sont pas des clauses. La
session qui finissait n'a qu'une loi légale, et il garde. La session qui
rappelait en a deux : ce passage prend « pas de second appel » et écarte.
L'autre loi reste légale. Sans seconde décision, ou si aucune loi ne mord,
rien n'est inventé.

Tau écrit la loi qui sert de raison. La source énonce le fait observé,
`o3[t] & o5[t]' != 0`, pas la loi. Le dual `sometimes o5[t]' o3[t] = 0`
n'y est pas. Lié au pas, la session qui finissait garde. Celle qui
rappelait écarte, et Tau met une fin. Sans cette violation, rien n'est écrit.

Tau nomme la violation. `v0 = 1`, `v1 = 1` et `p3 = 1` ne sont pas des
clauses. Le fait envoyé est celui qu'il a nommé. La session qui finissait
n'a qu'une violation, au pas 3, et il l'écarte. La session qui rappelait
en a deux : ce passage nomme le second appel, au pas 4, et il l'écarte.
L'autre reste légale. Sans violation, aucun fait n'est envoyé.

Tau écrit la phrase du fait. L'observation est les bits, pas la phrase.
`n` imprime une ligne qui n'est pas l'entrée, et qui porte `always`.
Cette ligne est le fait. Le dual en sort. Sans violation, aucune phrase
n'est écrite.

La formule donnée à `n` est lue sur le pas nommé, et sur le pas d'avant.
Ce n'est pas une phrase par sorte. Deux événements du même nom : rien
n'est écrit. Le témoin libre n'est pas le seul remplaçant : l'ensemble
légal est publié.

`n` imprime la clause nécessaire. Elle dit que le bit enregistré s'éteint.
Elle n'est pas dans l'entrée. Elle ne nomme pas le remplaçant. On n'en pose pas.

La même clause, réinstallée, laisse un `x` libre. `x1` et `x1'` ne sont
pas des bits. On ne les convertit pas. Le pas d'exécution n'est pas le pas
de la session. Le remplaçant n'est pas exécuté.

Épingler le bit observé ne retire pas le `x`. Le 0 d'un pas plus loin est
le `sometimes` qui se décharge ailleurs, pas le pas de la session. L'événement
n'est pas écrit. Le modèle du solveur reste un modèle.

La clause que `n` a imprimée, exécutée à son indice, fixe le bit.
`o2[3]' != 0` rend 0. `o4[4]' != 0` rend 0. Ce n'est pas un `sometimes`.
Les autres zéros ne sont pas lus. L'événement n'est toujours pas écrit.

La loi déjà écrite, jointe à cette clause, fait imprimer `d3' = 0`.
On n'a pas épinglé la fin. À son indice, ce bit vaut 1. L'événement est
une fin. Le modèle du solveur reste un résultat : on ne le copie pas.
Sur l'autre trajet, le pas d'avant n'est pas un résultat. La loi ne
s'applique pas. Rien n'est écrit.

Sur ce trajet, l'exécution met pourtant une fin à 1. Forcer l'assistant
ou le résultat marche aussi. Ce 1 est un modèle, pas l'événement.
On n'écrit pas ce pas. Là où la loi a imprimé la fin, le pas écrit
n'a que ce type : pas de statut, pas la suite du trajet.

Ce pas, rejoué, n'est plus une violation. Tau dit `no solution`.
Sur l'autre trajet, enlever notre « un événement » laisse le pas vide
possible, pas forcé. `n` n'éteint que l'appel. On n'efface pas le pas.

L'autre violation du même trajet, au pas 3, a la loi. `n` imprime
`d3' = 0`. Rejoué, `no solution`. Ce n'est pas le pas nommé. Le second
appel reste ouvert. On ne substitue pas.

La clause imprimée ne laisse qu'une paire sur la session qui finissait.
Sur l'autre, elle en laisse deux. Le témoin n'est pas la décision.
L'équation du point interdit de réviser l'appel en appel, et laisse
les trois autres. Aucun n'est imprimé allumé.

Le second maillon seul, `d4' & a3 = 0`, imprime `d4' = 0` si l'assistant
est épinglé. Ce n'est pas la fin qu'on garde.

Les deux lois jointes, sans épingler l'assistant, impriment la fin au
pas 3 et `a3 = 0`. Elles n'impriment pas la fin au pas 4. Cette fin
tardive ne tenait que par l'épingle que la première loi éteint. On ne
l'écrit pas. Le rejeu de la fin tôt est clos.

Le témoin qui nommait le second appel est après cette fin. Ce n'est
plus la violation terminée. La violation terminée est celle que la
clause jointe a close, au pas 3.

```bash
python3 scripts/write_rule.py
```

```bash
python3 scripts/revise_session.py
```

## Lot de trajectoires

Sept chemins, sept formes. Le harness Python les accepte tous. Tau en accepte
4 et en refuse 3 : appel sans décision antérieure, décision placée après
l'appel, fin sans décision.

```bash
python3 scripts/trajectory_portfolio.py
```

Le rapport est `trajectory_portfolio.json`. Un lot sans forme distincte, ou
sans cas `UNSAT`, n'est pas une preuve.

## Traces locales

`scripts/local_traces.py` lit les sessions Hermes du disque, sans texte et sans
arguments. Sur 2039 sessions avec outils : 1743 passent le harness, 296
échouent (221 appels sans résultat, 75 sans fin). Tau a jugé les 1743 sessions
terminées et appariées : 1743 `SAT`, 0 `UNSAT`. Les 241 plus courtes portent
tous les liens. Les 1502 autres portent le lien « décision avant appel »,
renuméroté en t=1,2, y compris une session de 392 appels. Le coût suivait
l'indice de temps, pas le nombre de liens.

```bash
python3 scripts/local_traces.py --packed-ceiling 48
```

## Porte Tau de transition, exemple manuel

Le noyau `tau/agent_transition.tau` reste l'exemple écrit à la main de la même
forme. `scripts/run_tau_gate.py` sans `--trace` l'exécute encore. Il ne juge
pas la trace passée à la mission.

```bash
python3 scripts/run_tau_gate.py
```

Le rapport est écrit dans `tau/verdict.json`. La CI exécute les tests Python ;
elle n'exécute pas Tau, le binaire n'y est pas installé.

## État du projet

- adaptateurs Hermes et Claude Code vers une trace canonique ;
- validation des outils, appels, résultats et terminaison ;
- replay déterministe par fixtures ;
- mutations : outil interdit, résultat orphelin, arrêt prématuré, résultat ignoré ;
- propriétés Tau émises depuis chaque trace, exécutées localement (`SAT` /
  `UNSAT` / contrôle libre) ;
- comparaison multi-agents sur la spec de chacun, pas sur un noyau partagé ;
- lot de 7 trajectoires distinctes : le harness les accepte toutes, Tau en
  refuse 3 ;
- traces locales : 2039 sessions, 1743 harness vert, Tau 1743/1743 `SAT`
  (241 liens complets, 1502 ordre renuméroté) ; 296 ouvertes non jugées.

Le projet conserve volontairement une séparation stricte entre le runtime de
l'agent, l'adaptation de sa trace et la vérification indépendante.
